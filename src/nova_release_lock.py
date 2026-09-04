"""Fail-closed orchestration for Nova source release snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Sequence

from nova_release_gates import (
    GateDefinition,
    GateResult,
    GateRunner,
    default_gate_definitions,
)
from nova_release_manifest import release_state_root, write_json_atomic
from nova_release_manifest import build_content_manifest, canonical_json
from nova_release_policy import (
    SnapshotClass,
    SnapshotDecision,
    SnapshotPolicy,
    SnapshotReport,
    scan_workspace,
)
from nova_release_worktree import (
    GitRepository,
    PromotionError,
    apply_snapshot,
    cleanup_worktree,
    commit_candidate,
    create_candidate_worktree,
    git_output,
    list_deleted_paths,
    list_tracked_paths,
    promote_candidate,
    remove_candidate_paths,
)
from nova_release_security import inspect_release


RELEASE_LOCK_SCHEMA_VERSION = "1.0"
_RUN_ID_PATTERN = re.compile(
    r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{7,12}-[0-9a-f]{4}"
)


class ReleaseStatus(str, Enum):
    PLANNED = "PLANNED"
    BUILDING = "BUILDING"
    VERIFIED = "VERIFIED"
    PROMOTED = "PROMOTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ReleasePaths:
    run_dir: Path
    candidate_worktree: Path
    master_worktree: Path
    preflight_report: Path
    gate_report: Path
    run_report: Path


@dataclass
class ReleaseRun:
    run_id: str
    status: ReleaseStatus
    source_branch: str
    source_commit: str
    master_before: str
    paths: ReleasePaths
    snapshot_report: SnapshotReport
    candidate_branch: str | None = None
    candidate_commit: str | None = None
    master_after: str | None = None
    rollback_ref: str | None = None
    failure_gate: str | None = None
    report_path: Path | None = None


@dataclass(frozen=True)
class PromotionResult:
    status: ReleaseStatus
    master_before: str
    master_after: str
    candidate_commit: str
    rollback_ref: str
    rollback_command: list[str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_to_dict(report: SnapshotReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "decisions": [
            {
                **asdict(decision),
                "classification": decision.classification.value,
            }
            for decision in report.decisions
        ],
    }


def _snapshot_from_dict(payload: dict[str, object]) -> SnapshotReport:
    decisions = []
    for raw in payload.get("decisions", []):
        item = dict(raw)
        item["classification"] = SnapshotClass(str(item["classification"]))
        decisions.append(SnapshotDecision(**item))
    return SnapshotReport(
        schema_version=str(payload["schema_version"]),
        decisions=decisions,
    )


class NovaReleaseLock:
    """Build and promote one verified release without mutating its source tree."""

    def __init__(
        self,
        repo_root: str | Path,
        temp_root: str | Path | None = None,
        *,
        policy_path: str | Path | None = None,
        gate_definitions: Sequence[GateDefinition] | None = None,
    ) -> None:
        self.repository = GitRepository.discover(repo_root)
        self.repo_root = self.repository.root
        self.temp_root = Path(
            temp_root
            if temp_root is not None
            else Path(tempfile.gettempdir()) / "nova-release-lock"
        ).absolute()
        self.policy_path = Path(
            policy_path
            if policy_path is not None
            else self.repo_root / "config" / "nova_release_snapshot_policy.json"
        ).absolute()
        self.gate_definitions = (
            tuple(gate_definitions) if gate_definitions is not None else None
        )

    def _new_run_id(self, source_commit: str) -> str:
        timestamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{source_commit[:12]}-{secrets.token_hex(2)}"

    def _release_paths(self, run_id: str) -> ReleasePaths:
        state_root = release_state_root(self.repository.common_dir)
        run_dir = state_root / "runs" / run_id
        repository_hash = hashlib.sha256(
            str(self.repo_root).casefold().encode("utf-8")
        ).hexdigest()[:12]
        temporary_run = self.temp_root / repository_hash / run_id
        return ReleasePaths(
            run_dir=run_dir,
            candidate_worktree=temporary_run / "candidate",
            master_worktree=temporary_run / "master",
            preflight_report=run_dir / "preflight.json",
            gate_report=run_dir / "gates.json",
            run_report=run_dir / "run.json",
        )

    def _run_payload(self, run: ReleaseRun) -> dict[str, object]:
        return {
            "schema_version": RELEASE_LOCK_SCHEMA_VERSION,
            "run_id": run.run_id,
            "status": run.status.value,
            "source_branch": run.source_branch,
            "source_commit": run.source_commit,
            "master_before": run.master_before,
            "candidate_branch": run.candidate_branch,
            "candidate_commit": run.candidate_commit,
            "master_after": run.master_after,
            "rollback_ref": run.rollback_ref,
            "failure_gate": run.failure_gate,
            "report_path": str(run.paths.run_report),
            "paths": {name: str(value) for name, value in asdict(run.paths).items()},
            "snapshot_report": _snapshot_to_dict(run.snapshot_report),
        }

    def _persist_run(self, run: ReleaseRun) -> None:
        write_json_atomic(run.paths.run_report, self._run_payload(run))
        run.report_path = run.paths.run_report

    def preflight(self) -> ReleaseRun:
        source_branch = git_output(self.repo_root, "branch", "--show-current")
        if not source_branch:
            raise RuntimeError("release source must be on a named Git branch")
        source_commit = git_output(self.repo_root, "rev-parse", "HEAD")
        master_before = git_output(self.repo_root, "rev-parse", "refs/heads/master")
        policy = SnapshotPolicy.load(self.policy_path)
        snapshot = scan_workspace(
            self.repo_root,
            policy,
            list_tracked_paths(self.repo_root),
            list_deleted_paths(self.repo_root),
        )
        run_id = self._new_run_id(source_commit)
        paths = self._release_paths(run_id)
        candidate_branch = f"codex/release-lock-{run_id}"
        run = ReleaseRun(
            run_id=run_id,
            status=(ReleaseStatus.PLANNED if snapshot.passed else ReleaseStatus.FAILED),
            source_branch=source_branch,
            source_commit=source_commit,
            master_before=master_before,
            paths=paths,
            snapshot_report=snapshot,
            candidate_branch=candidate_branch,
            failure_gate=None if snapshot.passed else "snapshot_policy",
        )
        write_json_atomic(paths.preflight_report, _snapshot_to_dict(snapshot))
        self._persist_run(run)
        return run

    def load_run(self, run_id: str) -> ReleaseRun:
        if _RUN_ID_PATTERN.fullmatch(run_id) is None:
            raise ValueError("invalid Release Lock run ID")
        paths = self._release_paths(run_id)
        payload = json.loads(paths.run_report.read_text(encoding="utf-8"))
        if payload.get("run_id") != run_id:
            raise ValueError("Release Lock run report ID mismatch")
        run = ReleaseRun(
            run_id=run_id,
            status=ReleaseStatus(str(payload["status"])),
            source_branch=str(payload["source_branch"]),
            source_commit=str(payload["source_commit"]),
            master_before=str(payload["master_before"]),
            paths=paths,
            snapshot_report=_snapshot_from_dict(dict(payload["snapshot_report"])),
            candidate_branch=payload.get("candidate_branch"),
            candidate_commit=payload.get("candidate_commit"),
            master_after=payload.get("master_after"),
            rollback_ref=payload.get("rollback_ref"),
            failure_gate=payload.get("failure_gate"),
            report_path=paths.run_report,
        )
        return run

    @staticmethod
    def _gate_payload(result: GateResult) -> dict[str, object]:
        return asdict(result)

    def _fail(self, run: ReleaseRun, gate: str) -> ReleaseRun:
        run.status = ReleaseStatus.FAILED
        run.failure_gate = gate
        self._persist_run(run)
        return run

    def build(self, run: ReleaseRun | str) -> ReleaseRun:
        current = self.load_run(run) if isinstance(run, str) else run
        if current.status is not ReleaseStatus.PLANNED:
            raise ValueError("only a planned Release Lock run can be built")
        try:
            return self._build_planned(current)
        except BaseException:
            if current.status is not ReleaseStatus.FAILED:
                self._fail(current, "build_exception")
            raise

    def _build_planned(self, current: ReleaseRun) -> ReleaseRun:
        if git_output(self.repo_root, "rev-parse", "HEAD") != current.source_commit:
            return self._fail(current, "source_revision_changed")
        if (
            git_output(self.repo_root, "rev-parse", "refs/heads/master")
            != current.master_before
        ):
            return self._fail(current, "master_revision_changed")

        current.status = ReleaseStatus.BUILDING
        self._persist_run(current)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        current.paths.candidate_worktree.parent.mkdir(parents=True, exist_ok=True)
        create_candidate_worktree(
            self.repository,
            current.source_commit,
            str(current.candidate_branch),
            current.paths.candidate_worktree,
            self.temp_root,
        )
        apply_snapshot(
            self.repo_root,
            current.paths.candidate_worktree,
            current.snapshot_report,
            self.temp_root,
        )

        baseline_manifest = build_content_manifest(
            current.paths.candidate_worktree,
            source_branch=current.source_branch,
            source_commit=current.source_commit,
            candidate_branch=str(current.candidate_branch),
            excluded_counts={},
            deletions=[],
            gates={},
        )

        security = inspect_release(current.paths.candidate_worktree)
        if not security.passed:
            write_json_atomic(
                current.paths.gate_report,
                {"security": security.to_dict(), "gates": []},
            )
            return self._fail(current, "release_security")
        definitions = (
            list(self.gate_definitions)
            if self.gate_definitions is not None
            else default_gate_definitions(
                current.paths.candidate_worktree,
                current.paths.run_dir,
            )
        )
        runner = GateRunner(
            current.paths.candidate_worktree,
            current.paths.run_dir,
        )
        results: list[GateResult] = []
        for definition in definitions:
            result = runner.run(definition)
            results.append(result)
            write_json_atomic(
                current.paths.gate_report,
                {
                    "security": security.to_dict(),
                    "gates": [self._gate_payload(item) for item in results],
                },
            )
            if not result.passed:
                return self._fail(current, result.name)

        after_gates = build_content_manifest(
            current.paths.candidate_worktree,
            source_branch=current.source_branch,
            source_commit=current.source_commit,
            candidate_branch=str(current.candidate_branch),
            excluded_counts={},
            deletions=[],
            gates={},
        )
        baseline_files = {item.path: item for item in baseline_manifest.files}
        current_files = {item.path: item for item in after_gates.files}
        changed_paths = {
            path
            for path in baseline_files.keys() & current_files.keys()
            if baseline_files[path] != current_files[path]
        }
        removed_paths = baseline_files.keys() - current_files.keys()
        if changed_paths or removed_paths:
            return self._fail(current, "gate_modified_candidate")
        policy = SnapshotPolicy.load(self.policy_path)
        cleanup_roots: set[str] = set()
        for path in sorted(current_files.keys() - baseline_files.keys()):
            parts = path.split("/")
            excluded_root = None
            for index in range(1, len(parts) + 1):
                prefix = "/".join(parts[:index])
                contains_baseline_file = any(
                    baseline_path == prefix
                    or baseline_path.startswith(prefix + "/")
                    for baseline_path in baseline_files
                )
                if (
                    policy.classify(prefix).classification is SnapshotClass.EXCLUDE
                    and not contains_baseline_file
                ):
                    excluded_root = prefix
                    break
            if excluded_root is None:
                return self._fail(current, "gate_modified_candidate")
            cleanup_roots.add(excluded_root)
        if cleanup_roots:
            remove_candidate_paths(
                current.paths.candidate_worktree,
                cleanup_roots,
                self.temp_root,
                self.repo_root,
            )
            after_cleanup = build_content_manifest(
                current.paths.candidate_worktree,
                source_branch=current.source_branch,
                source_commit=current.source_commit,
                candidate_branch=str(current.candidate_branch),
                excluded_counts={},
                deletions=[],
                gates={},
            )
            if after_cleanup.files != baseline_manifest.files:
                return self._fail(current, "gate_modified_candidate")
        excluded_counts: dict[str, int] = {}
        for decision in current.snapshot_report.excluded:
            excluded_counts[decision.rule] = excluded_counts.get(decision.rule, 0) + 1
        deletions = [
            decision.path
            for decision in current.snapshot_report.decisions
            if decision.change == "deleted"
            and decision.classification is SnapshotClass.INCLUDE
        ]
        gate_status = {result.name: result.passed for result in results}
        manifest = build_content_manifest(
            current.paths.candidate_worktree,
            source_branch=current.source_branch,
            source_commit=current.source_commit,
            candidate_branch=str(current.candidate_branch),
            excluded_counts=excluded_counts,
            deletions=deletions,
            gates=gate_status,
        )
        manifest_path = current.paths.candidate_worktree / "NOVA_RELEASE_MANIFEST.json"
        write_json_atomic(manifest_path, manifest.to_dict())
        repeated = build_content_manifest(
            current.paths.candidate_worktree,
            source_branch=current.source_branch,
            source_commit=current.source_commit,
            candidate_branch=str(current.candidate_branch),
            excluded_counts=excluded_counts,
            deletions=deletions,
            gates=gate_status,
        )
        if canonical_json(manifest.to_dict()) != canonical_json(repeated.to_dict()):
            return self._fail(current, "manifest_determinism")

        current.candidate_commit = commit_candidate(
            current.paths.candidate_worktree,
            f"release: lock Nova snapshot {manifest.release_id}",
        )
        if git_output(current.paths.candidate_worktree, "status", "--short"):
            return self._fail(current, "candidate_not_clean")
        current.status = ReleaseStatus.VERIFIED
        current.failure_gate = None
        self._persist_run(current)
        return current

    def promote(self, run_id: str) -> PromotionResult:
        current = self.load_run(run_id)
        if current.status is not ReleaseStatus.VERIFIED:
            raise ValueError("only a verified Release Lock run can be promoted")
        if not current.candidate_commit:
            raise ValueError("verified Release Lock run has no candidate commit")
        current.paths.master_worktree.parent.mkdir(parents=True, exist_ok=True)
        try:
            promoted = promote_candidate(
                self.repository,
                candidate_commit=current.candidate_commit,
                master_before=current.master_before,
                destination=current.paths.master_worktree,
                approved_temp_root=self.temp_root,
                run_id=current.run_id,
            )
        except PromotionError as error:
            self._fail(current, error.code)
            raise
        except BaseException:
            self._fail(current, "promotion_exception")
            raise
        current.status = ReleaseStatus.PROMOTED
        current.master_after = promoted.master_after
        current.rollback_ref = promoted.rollback_ref
        current.failure_gate = None
        self._persist_run(current)
        rollback_command = [
            "git",
            "-C",
            str(self.repo_root),
            "revert",
            "-m",
            "1",
            promoted.master_after,
        ]
        return PromotionResult(
            status=current.status,
            master_before=current.master_before,
            master_after=promoted.master_after,
            candidate_commit=promoted.candidate_commit,
            rollback_ref=promoted.rollback_ref,
            rollback_command=rollback_command,
        )

    def cleanup(self, run_id: str) -> ReleaseRun:
        current = self.load_run(run_id)
        for path in (
            current.paths.candidate_worktree,
            current.paths.master_worktree,
        ):
            if path.exists():
                cleanup_worktree(
                    self.repository,
                    path,
                    self.temp_root,
                )
        return self.load_run(run_id)
