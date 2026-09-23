"""Minimal end-to-end proof-job orchestrator for Nova Creature."""

from __future__ import annotations

from pathlib import Path
from shutil import copytree
import hashlib
from html import escape
import json
import subprocess
import sys
from typing import Any, Callable

from .agent_run import AgentRun, AgentRunState
from .agent_report import (
    OrchestratedRunResult,
    StructuredAgentReport,
    StructuredAgentReportSection,
)
from .contracts import build_run_contract, sha256_json
from .memory_provenance import build_provenance_record, write_provenance_memory
from .verification_playwright import verify_playwright_page


class _WorkspaceMemoryJournal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add_memory(
        self,
        content: str,
        *,
        source: str,
        write_reason: str,
        confidence: float,
        previous_version_hash: str | None = None,
        rollback_point: str | None = None,
        metadata: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "content": content,
            "source": source,
            "write_reason": write_reason,
            "confidence": confidence,
            "previous_version_hash": previous_version_hash,
            "rollback_point": rollback_point,
            "metadata": dict(metadata or {}),
            "provenance": dict(provenance or {}),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return payload

    def write(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.add_memory(*args, **kwargs)


def _copy_project(project_root: Path, workspace_root: Path) -> None:
    if workspace_root.exists():
        raise FileExistsError(f"Workspace already exists: {workspace_root}")
    copytree(project_root, workspace_root)


def _update_app_module(workspace_root: Path) -> tuple[Path, str, str]:
    app_path = workspace_root / "app.py"
    if not app_path.exists():
        raise FileNotFoundError(f"Expected app.py in {workspace_root}")
    original = app_path.read_text(encoding="utf-8")
    updated = original
    if 'return "hello"' in updated:
        updated = updated.replace('return "hello"', 'return "hello, nova"')
    elif "return 'hello'" in updated:
        updated = updated.replace("return 'hello'", 'return "hello, nova"')
    elif 'return "hello, nova"' not in updated:
        updated = original + '\n\n\ndef upgraded_message():\n    return "hello, nova"\n'
    if updated == original:
        raise ValueError("Proof job could not identify a safe change to apply to app.py")
    app_path.write_text(updated, encoding="utf-8")
    return app_path, sha256_json(original), sha256_json(updated)


def _run_bounded(command: list[str], workspace_root: Path, timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, cwd=workspace_root, text=True,
                              capture_output=True, check=False, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        return subprocess.CompletedProcess(command, 124, stdout,
                                           f"Subprocess timeout after {timeout_seconds} seconds")


def _run_pytest(workspace_root: Path) -> subprocess.CompletedProcess[str]:
    return _run_bounded([sys.executable, "-m", "pytest", "-q"], workspace_root, 120)


def _run_app(workspace_root: Path) -> subprocess.CompletedProcess[str]:
    # A child process bounds runtime; it does NOT restrict filesystem/network access.
    script = """import app
for name in ('answer', 'greeting', 'main', 'upgraded_message'):
    fn = getattr(app, name, None)
    if callable(fn):
        print(fn())
        break
else:
    raise RuntimeError('No proof entry point found')
"""
    return _run_bounded([sys.executable, "-c", script], workspace_root, 20)


def run_proof_job(
    *,
    project_root: str | Path,
    output_dir: str | Path | None = None,
    page_factory: Callable[[], Any] | None = None,
    browser_factory: Callable[[], Any] | None = None,
    gateway_core: Any | None = None,
) -> OrchestratedRunResult:
    project_root = Path(project_root).resolve()
    if not project_root.exists():
        raise FileNotFoundError(project_root)

    workspace_root = Path(output_dir or (project_root.parent / f"{project_root.name}.nova-proof")).resolve()
    _copy_project(project_root, workspace_root)

    run_id = "proof_" + sha256_json({"root": str(project_root), "goal": "proof"} )[:12]
    contract = build_run_contract(
        run_id=run_id,
        goal="Read a project, edit one file, run tests, verify with Playwright, and preserve rollback evidence.",
        owner_id="nova",
        project_id=project_root.name,
        workspace_root=str(workspace_root),
        allowed_roots=[str(workspace_root)],
        allowed_tools=["filesystem.read", "filesystem.write", "terminal.run", "playwright.verify"],
        allowed_resources=["filesystem://workspace", "terminal://workspace", "browser://workspace"],
        time_budget_seconds=300,
        tool_budget=12,
        cost_budget=0.0,
        memory_budget=8,
        metadata={"proof_job": True, "isolation": {
            "kind": "copied_workspace", "os_sandbox": False,
            "host_filesystem_access_restricted": False,
            "network_access_restricted": False,
            "subprocess_timeout_seconds": {"app": 20, "pytest": 120},
            "authorization": "caller_invocation_for_trusted_project",
        }},
    )
    run = AgentRun.create(contract)
    run.transition(AgentRunState.AUTHORIZED, reason="proof job authorized")
    run.transition(AgentRunState.EXECUTING, reason="proof job executing")

    original_app = workspace_root / "app.py"
    original_bytes = original_app.read_bytes()
    rollback_path = workspace_root / "rollback" / "app.py.original"
    rollback_path.parent.mkdir(parents=True, exist_ok=True)
    rollback_path.write_bytes(original_bytes)
    baseline_hash = sha256_json(original_app.read_text(encoding="utf-8"))
    try:
        modified_app, before_hash, after_hash = _update_app_module(workspace_root)
        if before_hash != baseline_hash:
            before_hash = baseline_hash

        app_result = _run_app(workspace_root)
        output_value = app_result.stdout.strip() if app_result.returncode == 0 else "App execution failed"

        pytest_result = _run_pytest(workspace_root)
        test_passed = pytest_result.returncode == 0 and app_result.returncode == 0

        html_path = workspace_root / "proof.html"
        html_path.write_text(
            f"<html><body><main><h1>{escape(output_value)}</h1><p>Nova proof job</p></main></body></html>",
            encoding="utf-8",
        )
        run.transition(AgentRunState.VERIFYING, reason="browser verification")
        verification = verify_playwright_page(
            html_path.as_uri(),
            [{"type": "contains", "contains": "hello, nova"}],
            timeout_seconds=20,
            output_dir=workspace_root / "playwright_evidence",
            page_factory=page_factory,
            browser_factory=browser_factory,
        )

    except Exception:
        original_app.write_bytes(original_bytes)
        run.transition(AgentRunState.ROLLED_BACK, reason="execution error; app.py restored")
        raise

    succeeded = test_passed and verification.passed
    restored = False
    if not succeeded:
        modified_app.write_bytes(original_bytes)
        restored = modified_app.read_bytes() == original_bytes
    else:
        memory_store = _WorkspaceMemoryJournal(workspace_root / "provenance_memory.jsonl")
        provenance = build_provenance_record(
            memory_id=f"memory-{run_id}",
            owner_id="nova",
            source=str(modified_app),
            timestamp=verification.verified_at,
            confidence=0.98,
            write_reason="proof_job_success",
            content=f"Updated {modified_app.name} and verified proof job output.",
            previous_version_hash=before_hash,
            rollback_point=str(rollback_path),
            metadata={
                "report_path": str(workspace_root / "agent_report.json"),
                "verification_hash": verification.dom_hash,
            },
        )
        write_provenance_memory(memory_store, provenance)


    rollback_available = rollback_path.is_file() and rollback_path.read_bytes() == original_bytes
    report = StructuredAgentReport(
        goal=contract.goal,
        plan=[
            "Read the project.",
            "Edit one file in a copied workspace (not an OS sandbox).",
            "Run tests.",
            "Verify the browser output.",
            "Write provenance memory and publish a structured report.",
        ],
        tools_used=["filesystem.read", "filesystem.write", "terminal.run", "playwright.verify"],
        files_changed=[str(modified_app.relative_to(workspace_root))],
        tests_executed=["python -m pytest -q"],
        browser_evidence={
            "url": verification.url,
            "verification_backend": "fixture" if page_factory or browser_factory else "playwright",
            "passed": verification.passed,
            "page_title": verification.page_title,
            "screenshot_hash": verification.screenshot_hash,
            "dom_hash": verification.dom_hash,
            "console_summary": verification.console_summary,
            "network_summary": verification.network_summary,
        },
        failures_and_retries=[] if test_passed and verification.passed else [
            {
                "phase": "app" if app_result.returncode else ("test" if not test_passed else "verification"),
                "app_returncode": app_result.returncode,
                "app_stderr": app_result.stderr[-2000:],
                "returncode": pytest_result.returncode,
                "stdout": pytest_result.stdout[-2000:],
                "stderr": pytest_result.stderr[-2000:],
            }
        ],
        final_verification={
            "passed": bool(test_passed and verification.passed),
            "pytest_returncode": pytest_result.returncode,
            "browser_passed": verification.passed,
            "app_returncode": app_result.returncode,
            "isolation": contract.metadata["isolation"],
        },
        unresolved_blockers=[] if test_passed and verification.passed else ["proof job did not fully verify"],
        rollback_information={
            "available": rollback_available,
            "original_hash": before_hash,
            "updated_hash": after_hash,
            "rollback_point": str(rollback_path),
            "original_bytes_sha256": hashlib.sha256(original_bytes).hexdigest(),
            "restored": restored,
            "scope": "app.py only; arbitrary subprocess side effects are not reverted",
        },
        sections=[
            StructuredAgentReportSection(
                title="plan",
                content=" -> ".join(["read", "edit", "test", "verify", "report"]),
                metadata={"goal_hash": contract.goal_hash},
            ),
            StructuredAgentReportSection(
                title="verification",
                content="Browser verification completed" if verification.passed else "Browser verification failed",
                metadata={"screenshot_hash": verification.screenshot_hash},
            ),
        ],
    )

    report_path = workspace_root / "agent_report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    if test_passed and verification.passed:
        run.transition(AgentRunState.COMPLETED, reason="proof job completed")
    elif restored:
        run.transition(AgentRunState.ROLLED_BACK, reason="proof job failed verification; app.py restored")
    else:
        run.transition(AgentRunState.FAILED, reason="proof job failed")

    if gateway_core is not None and hasattr(gateway_core, "register_agent_run"):
        gateway_core.register_agent_run(
            run=run,
            report=report,
            report_path=report_path,
            workspace_root=workspace_root,
            proof_artifacts={
                "pytest_stdout": pytest_result.stdout,
                "pytest_stderr": pytest_result.stderr,
                "verification": verification.to_dict(),
            },
        )

    return OrchestratedRunResult(
        run=run,
        report=report,
        workspace_root=str(workspace_root),
        report_path=str(report_path),
        proof_artifacts={
            "pytest_stdout": pytest_result.stdout,
            "pytest_stderr": pytest_result.stderr,
            "verification": verification.to_dict(),
        },
    )


__all__ = [
    "OrchestratedRunResult",
    "run_proof_job",
]
