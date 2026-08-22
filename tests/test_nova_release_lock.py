from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nova_release_gates import GateDefinition
from nova_release_lock import NovaReleaseLock, ReleaseStatus
from nova_release_worktree import GitError


ROOT = Path(__file__).resolve().parents[1]
POLICY_SOURCE = ROOT / "config" / "nova_release_snapshot_policy.json"


def run_git(root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def make_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    run_git(root, "init", "-b", "master")
    run_git(root, "config", "user.name", "Nova Release Test")
    run_git(root, "config", "user.email", "nova-release@example.invalid")
    (root / "src").mkdir()
    (root / "src" / "nova.py").write_text("committed\n", encoding="utf-8")
    (root / "config").mkdir()
    shutil.copy2(POLICY_SOURCE, root / "config" / POLICY_SOURCE.name)
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "initial")
    run_git(root, "switch", "-c", "codex/test-release-source")
    (root / "src" / "nova.py").write_text("working copy\n", encoding="utf-8")
    return root


def git_head(root: Path, ref: str = "HEAD") -> str:
    return run_git(root, "rev-parse", ref)


def advance_ref_without_checkout(root: Path, ref: str) -> str:
    parent = git_head(root, ref)
    tree = run_git(root, "rev-parse", f"{ref}^{{tree}}")
    completed = subprocess.run(
        ["git", "-C", str(root), "commit-tree", tree, "-p", parent],
        input="advance ref\n",
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    commit = completed.stdout.strip()
    run_git(root, "update-ref", f"refs/heads/{ref}", commit, parent)
    return commit


def failing_gate() -> GateDefinition:
    return GateDefinition(
        name="forced_failure",
        argv=(sys.executable, "-c", "raise SystemExit(9)"),
        timeout_seconds=5,
    )


def passing_gate() -> GateDefinition:
    return GateDefinition(
        name="forced_success",
        argv=(sys.executable, "-c", "print('verified')"),
        timeout_seconds=5,
    )


def test_preflight_writes_report_and_blocks_ambiguous_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    master_before = git_head(repo, "master")
    (repo / "mystery.exe").write_bytes(b"MZ")
    lock = NovaReleaseLock(repo_root=repo, temp_root=tmp_path / "release-temp")

    result = lock.preflight()

    assert result.status is ReleaseStatus.FAILED
    assert result.failure_gate == "snapshot_policy"
    assert [item.path for item in result.snapshot_report.ambiguous] == ["mystery.exe"]
    assert result.report_path is not None
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "FAILED"
    assert report["failure_gate"] == "snapshot_policy"
    assert git_head(repo, "master") == master_before
    assert not result.paths.candidate_worktree.exists()


def test_build_stops_before_commit_when_gate_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    master_before = git_head(repo, "master")
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[failing_gate()],
    )

    planned = lock.preflight()
    assert planned.status is ReleaseStatus.PLANNED
    result = lock.build(planned)

    assert result.status is ReleaseStatus.FAILED
    assert result.failure_gate == "forced_failure"
    assert result.candidate_commit is None
    assert result.paths.candidate_worktree.is_dir()
    assert git_head(repo, "master") == master_before
    assert (repo / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"


def test_build_commits_verified_candidate_with_deterministic_manifest(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path / "repo")
    master_before = git_head(repo, "master")
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[passing_gate()],
    )

    result = lock.build(lock.preflight())

    assert result.status is ReleaseStatus.VERIFIED
    assert result.failure_gate is None
    assert result.candidate_commit == git_head(result.paths.candidate_worktree)
    assert run_git(result.paths.candidate_worktree, "status", "--short") == ""
    assert (
        result.paths.candidate_worktree / "src" / "nova.py"
    ).read_text(encoding="utf-8") == "working copy\n"
    manifest_path = result.paths.candidate_worktree / "NOVA_RELEASE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["candidate_branch"] == result.candidate_branch
    assert "NOVA_RELEASE_MANIFEST.json" not in {
        item["path"] for item in manifest["files"]
    }
    assert manifest["gates"] == [{"name": "forced_success", "passed": True}]
    assert git_head(repo, "master") == master_before
    assert (repo / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"


def test_build_fails_when_source_head_changes_after_preflight(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[passing_gate()],
    )
    planned = lock.preflight()
    (repo / "src" / "new.py").write_text("new\n", encoding="utf-8")
    run_git(repo, "add", "src/new.py")
    run_git(repo, "commit", "-m", "move source head")

    result = lock.build(planned)

    assert result.status is ReleaseStatus.FAILED
    assert result.failure_gate == "source_revision_changed"
    assert result.candidate_commit is None
    assert not result.paths.candidate_worktree.exists()


def test_build_fails_when_master_changes_after_preflight(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[passing_gate()],
    )
    planned = lock.preflight()
    changed_master = advance_ref_without_checkout(repo, "master")

    result = lock.build(planned)

    assert result.status is ReleaseStatus.FAILED
    assert result.failure_gate == "master_revision_changed"
    assert git_head(repo, "master") == changed_master
    assert result.candidate_commit is None
    assert not result.paths.candidate_worktree.exists()


def test_build_fails_security_scan_before_running_gates(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    marker = tmp_path / "gate-ran.txt"
    gate = GateDefinition(
        name="must_not_run",
        argv=(
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
        ),
        timeout_seconds=5,
    )
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[gate],
    )
    planned = lock.preflight()
    (repo / "src" / "nova.py").write_text(
        'api_key = "sk-abcdefghijklmnopqrstuvwxyz012345"\n',
        encoding="utf-8",
    )

    result = lock.build(planned)

    assert result.status is ReleaseStatus.FAILED
    assert result.failure_gate == "release_security"
    assert result.candidate_commit is None
    assert not marker.exists()
    gate_report = json.loads(result.paths.gate_report.read_text(encoding="utf-8"))
    assert gate_report["security"]["secret_findings"] == ["src/nova.py"]


def test_build_rejects_gate_mutation_of_candidate(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    gate = GateDefinition(
        name="mutating_gate",
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; Path('generated.py').write_text('changed')",
        ),
        timeout_seconds=5,
    )
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[gate],
    )

    result = lock.build(lock.preflight())

    assert result.status is ReleaseStatus.FAILED
    assert result.failure_gate == "gate_modified_candidate"
    assert result.candidate_commit is None
    assert (result.paths.candidate_worktree / "generated.py").is_file()


def test_build_removes_gate_generated_excluded_artifact(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    gate = GateDefinition(
        name="excluded_artifact_gate",
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sandbox').mkdir(); "
            "Path('sandbox/result.json').write_text('{}')",
        ),
        timeout_seconds=5,
    )
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[gate],
    )

    result = lock.build(lock.preflight())

    assert result.status is ReleaseStatus.VERIFIED
    assert not (result.paths.candidate_worktree / "sandbox").exists()
    manifest = json.loads(
        (result.paths.candidate_worktree / "NOVA_RELEASE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    assert not any(item["path"].startswith("sandbox/") for item in manifest["files"])


def test_build_exception_persists_failed_state(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=repo / "unsafe-release-temp",
        gate_definitions=[passing_gate()],
    )
    planned = lock.preflight()

    with pytest.raises(Exception):
        lock.build(planned)

    persisted = lock.load_run(planned.run_id)
    assert persisted.status is ReleaseStatus.FAILED
    assert persisted.failure_gate == "build_exception"
    assert persisted.candidate_commit is None


def make_verified_release(tmp_path: Path) -> tuple[Path, NovaReleaseLock, str]:
    repo = make_repo(tmp_path / "repo")
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[passing_gate()],
    )
    verified = lock.build(lock.preflight())
    assert verified.status is ReleaseStatus.VERIFIED
    return repo, lock, verified.run_id


def test_promote_creates_rollback_ref_and_merge_commit(tmp_path: Path) -> None:
    repo, lock, run_id = make_verified_release(tmp_path)
    source_text = (repo / "src" / "nova.py").read_text(encoding="utf-8")

    result = lock.promote(run_id)

    assert result.status is ReleaseStatus.PROMOTED
    assert git_head(repo, "master") == result.master_after
    assert git_head(repo, result.rollback_ref) == result.master_before
    parents = run_git(repo, "show", "-s", "--format=%P", result.master_after).split()
    assert parents == [result.master_before, result.candidate_commit]
    assert result.rollback_command == [
        "git",
        "-C",
        str(repo),
        "revert",
        "-m",
        "1",
        result.master_after,
    ]
    assert (repo / "src" / "nova.py").read_text(encoding="utf-8") == source_text
    assert run_git(repo, "status", "--short") == "M src/nova.py"


def test_promote_fails_closed_when_master_moved(tmp_path: Path) -> None:
    repo, lock, run_id = make_verified_release(tmp_path)
    changed_master = advance_ref_without_checkout(repo, "master")

    with pytest.raises(GitError, match="master changed"):
        lock.promote(run_id)

    persisted = lock.load_run(run_id)
    assert persisted.status is ReleaseStatus.FAILED
    assert persisted.failure_gate == "promotion_master_changed"
    assert persisted.master_after is None
    assert git_head(repo, "master") == changed_master


def test_promote_aborts_conflict_and_preserves_master(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    master_seed = tmp_path / "master-seed"
    run_git(repo, "worktree", "add", str(master_seed), "master")
    (master_seed / "src" / "nova.py").write_text("master version\n", encoding="utf-8")
    run_git(master_seed, "add", "src/nova.py")
    run_git(master_seed, "commit", "-m", "diverge master")
    run_git(repo, "worktree", "remove", str(master_seed))
    master_before = git_head(repo, "master")
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[passing_gate()],
    )
    verified = lock.build(lock.preflight())

    with pytest.raises(GitError, match="merge conflicted"):
        lock.promote(verified.run_id)

    persisted = lock.load_run(verified.run_id)
    assert persisted.status is ReleaseStatus.FAILED
    assert persisted.failure_gate == "promotion_conflict"
    assert persisted.master_after is None
    assert git_head(repo, "master") == master_before
    assert run_git(persisted.paths.master_worktree, "status", "--short") == ""
    rollback = f"codex/rollback-release-lock-{verified.run_id}"
    assert git_head(repo, rollback) == master_before


def test_promote_refuses_master_checked_out_elsewhere(tmp_path: Path) -> None:
    repo, lock, run_id = make_verified_release(tmp_path)
    checked_out = tmp_path / "checked-out-master"
    run_git(repo, "worktree", "add", str(checked_out), "master")
    master_before = git_head(repo, "master")

    with pytest.raises(GitError, match="already checked out"):
        lock.promote(run_id)

    persisted = lock.load_run(run_id)
    assert persisted.status is ReleaseStatus.FAILED
    assert persisted.failure_gate == "promotion_master_checked_out"
    assert git_head(repo, "master") == master_before
    rollback = f"codex/rollback-release-lock-{run_id}"
    assert run_git(repo, "branch", "--list", rollback) == ""


def test_promote_cannot_run_twice(tmp_path: Path) -> None:
    repo, lock, run_id = make_verified_release(tmp_path)
    first = lock.promote(run_id)

    with pytest.raises(ValueError, match="only a verified"):
        lock.promote(run_id)

    assert git_head(repo, "master") == first.master_after
    persisted = lock.load_run(run_id)
    assert persisted.status is ReleaseStatus.PROMOTED


def run_cli(repo: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "nova_release_lock.py"),
            "--repo",
            str(repo),
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
    )


def test_cli_defaults_to_plan_and_never_promotes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    master_before = git_head(repo, "master")

    completed = run_cli(repo, [])

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0, completed.stderr
    assert payload["operation"] == "plan"
    assert payload["status"] == "PLANNED"
    assert payload["promoted"] is False
    assert payload["candidate_commit"] is None
    assert git_head(repo, "master") == master_before


def test_cli_promote_requires_explicit_run_id(tmp_path: Path) -> None:
    completed = run_cli(tmp_path, ["promote"])

    assert completed.returncode == 2
    assert "--run-id" in completed.stderr


def test_cleanup_removes_worktrees_but_preserves_refs_and_reports(tmp_path: Path) -> None:
    repo, lock, run_id = make_verified_release(tmp_path)
    promoted = lock.promote(run_id)
    persisted = lock.load_run(run_id)
    candidate_path = persisted.paths.candidate_worktree
    master_path = persisted.paths.master_worktree
    candidate_branch = str(persisted.candidate_branch)
    report_path = persisted.paths.run_report

    result = lock.cleanup(run_id)

    assert result.status is ReleaseStatus.PROMOTED
    assert not candidate_path.exists()
    assert not master_path.exists()
    assert git_head(repo, candidate_branch) == promoted.candidate_commit
    assert git_head(repo, promoted.rollback_ref) == promoted.master_before
    assert report_path.is_file()


def test_cli_rejects_malformed_run_id_without_traceback(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")

    completed = run_cli(repo, ["status", "--run-id", "../private"])

    assert completed.returncode == 2
    payload = json.loads(completed.stderr)
    assert payload["error"] == "unsafe_state"
    assert "invalid Release Lock run ID" in payload["message"]
    assert "Traceback" not in completed.stderr


def load_cli_module():
    spec = importlib.util.spec_from_file_location(
        "nova_release_lock_cli_test",
        ROOT / "tools" / "nova_release_lock.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_end_to_end_in_disposable_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_repo(tmp_path / "repo")
    (repo / "data").mkdir()
    (repo / "data" / "private.db").write_bytes(b"private")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_new.py").write_text(
        "def test_new():\n    assert True\n",
        encoding="utf-8",
    )
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[passing_gate()],
    )
    cli = load_cli_module()
    factory = lambda **_kwargs: lock

    assert cli.main(
        ["--repo", str(repo), "plan"], controller_factory=factory
    ) == 0
    planned = json.loads(capsys.readouterr().out)
    assert cli.main(
        ["--repo", str(repo), "build", "--run-id", planned["run_id"]],
        controller_factory=factory,
    ) == 0
    built = json.loads(capsys.readouterr().out)
    candidate = lock.load_run(built["run_id"]).paths.candidate_worktree
    assert (candidate / "tests" / "test_new.py").is_file()
    assert not (candidate / "data" / "private.db").exists()

    assert cli.main(
        ["--repo", str(repo), "promote", "--run-id", built["run_id"]],
        controller_factory=factory,
    ) == 0
    promoted = json.loads(capsys.readouterr().out)
    assert promoted["promoted"] is True
    assert git_head(repo, promoted["rollback_ref"]) == promoted["master_before"]
    assert len(run_git(repo, "show", "-s", "--format=%P", "master").split()) == 2
    assert (repo / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"

    assert cli.main(
        ["--repo", str(repo), "cleanup", "--run-id", built["run_id"]],
        controller_factory=factory,
    ) == 0
    cleaned = json.loads(capsys.readouterr().out)
    assert cleaned["status"] == "PROMOTED"
    assert not candidate.exists()
