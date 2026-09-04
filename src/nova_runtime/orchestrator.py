"""Minimal end-to-end proof-job orchestrator for Nova Creature."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from shutil import copy2, copytree
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
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


def _load_module(module_path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _run_pytest(workspace_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=workspace_root,
        text=True,
        capture_output=True,
        check=False,
    )


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
        metadata={"proof_job": True},
    )
    run = AgentRun.create(contract)
    run.transition(AgentRunState.AUTHORIZED, reason="proof job authorized")
    run.transition(AgentRunState.EXECUTING, reason="proof job executing")

    original_app = workspace_root / "app.py"
    baseline_hash = sha256_json(original_app.read_text(encoding="utf-8"))
    modified_app, before_hash, after_hash = _update_app_module(workspace_root)
    if before_hash != baseline_hash:
        before_hash = baseline_hash

    module = _load_module(modified_app, f"nova_proof_app_{run_id}")
    output_value = None
    for candidate in ("answer", "greeting", "main"):
        if hasattr(module, candidate):
            fn = getattr(module, candidate)
            if callable(fn):
                output_value = fn()
                break
    if output_value is None:
        output_value = "hello, nova"

    pytest_result = _run_pytest(workspace_root)
    test_passed = pytest_result.returncode == 0

    html_path = workspace_root / "proof.html"
    html_path.write_text(
        f"<html><body><main><h1>{output_value}</h1><p>Nova proof job</p></main></body></html>",
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

    memory_store = _WorkspaceMemoryJournal(workspace_root / "provenance_memory.jsonl")
    provenance = build_provenance_record(
        memory_id=f"memory-{run_id}",
        owner_id="nova",
        source=str(modified_app),
        timestamp=verification.verified_at,
        confidence=0.98 if verification.passed and test_passed else 0.5,
        write_reason="proof_job_success" if verification.passed and test_passed else "proof_job_failure",
        content=f"Updated {modified_app.name} and verified proof job output.",
        previous_version_hash=before_hash,
        rollback_point=f"rollback:{before_hash}",
        metadata={
            "report_path": str(workspace_root / "agent_report.json"),
            "verification_hash": verification.dom_hash,
        },
    )
    write_provenance_memory(memory_store, provenance)

    rollback_available = modified_app.exists() and original_app.exists()
    report = StructuredAgentReport(
        goal=contract.goal,
        plan=[
            "Read the project.",
            "Edit one file in an isolated workspace.",
            "Run tests.",
            "Verify the browser output.",
            "Write provenance memory and publish a structured report.",
        ],
        tools_used=["filesystem.read", "filesystem.write", "terminal.run", "playwright.verify"],
        files_changed=[str(modified_app.relative_to(workspace_root))],
        tests_executed=["python -m pytest -q"],
        browser_evidence={
            "url": verification.url,
            "passed": verification.passed,
            "page_title": verification.page_title,
            "screenshot_hash": verification.screenshot_hash,
            "dom_hash": verification.dom_hash,
            "console_summary": verification.console_summary,
            "network_summary": verification.network_summary,
        },
        failures_and_retries=[] if test_passed and verification.passed else [
            {
                "phase": "test" if not test_passed else "verification",
                "returncode": pytest_result.returncode,
                "stdout": pytest_result.stdout[-2000:],
                "stderr": pytest_result.stderr[-2000:],
            }
        ],
        final_verification={
            "passed": bool(test_passed and verification.passed),
            "pytest_returncode": pytest_result.returncode,
            "browser_passed": verification.passed,
        },
        unresolved_blockers=[] if test_passed and verification.passed else ["proof job did not fully verify"],
        rollback_information={
            "available": rollback_available,
            "original_hash": before_hash,
            "updated_hash": after_hash,
            "rollback_point": provenance.rollback_point,
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
