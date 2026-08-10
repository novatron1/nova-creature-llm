import os
import subprocess
from pathlib import Path

import pytest

from nova_release_policy import SnapshotClass, SnapshotDecision, SnapshotReport
from nova_release_worktree import (
    AmbiguousSnapshotError,
    GitError,
    GitRepository,
    ReleasePathError,
    apply_snapshot,
    cleanup_worktree,
    commit_candidate,
    create_candidate_worktree,
    git_output,
    list_deleted_paths,
    list_tracked_paths,
)


def run_test_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def init_repo(root: Path) -> GitRepository:
    root.mkdir(parents=True)
    run_test_git(root, "init", "-b", "master")
    run_test_git(root, "config", "user.name", "Nova Release Test")
    run_test_git(root, "config", "user.email", "nova-release@example.invalid")
    (root / "src").mkdir()
    (root / "src" / "nova.py").write_text("committed\n", encoding="utf-8")
    run_test_git(root, "add", "src/nova.py")
    run_test_git(root, "commit", "-m", "initial")
    return GitRepository.discover(root)


def report_for(root: Path, include: list[str]) -> SnapshotReport:
    decisions = [
        SnapshotDecision(
            path=path,
            classification=SnapshotClass.INCLUDE,
            rule="test_include",
            tracked=run_test_git(root, "ls-files", "--", path) == path,
        )
        for path in include
    ]
    return SnapshotReport(schema_version="1.0", decisions=decisions)


def test_repository_discovery_and_inventory_observe_real_git_state(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    (source / "src" / "second.py").write_text("second\n", encoding="utf-8")
    run_test_git(source, "add", "src/second.py")
    run_test_git(source, "commit", "-m", "second")
    (source / "src" / "nova.py").unlink()
    run_test_git(source, "rm", "src/second.py")

    assert repo.root == source.resolve()
    assert repo.common_dir == (source / ".git").resolve()
    assert list_tracked_paths(source) == ["src/nova.py"]
    assert list_deleted_paths(source) == ["src/nova.py", "src/second.py"]


def test_git_output_raises_bounded_error_without_echoing_command_arguments(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path / "repo")
    secret = "release-secret-do-not-echo"

    with pytest.raises(GitError) as raised:
        git_output(repo.root, "show", secret)

    message = str(raised.value)
    assert secret not in message
    assert len(message) <= 2200


def test_candidate_overlay_preserves_source_worktree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    (source / "src" / "nova.py").write_text("working copy\n", encoding="utf-8")
    (source / "src" / "new.py").write_text("new\n", encoding="utf-8")
    report = report_for(source, include=["src/nova.py", "src/new.py"])
    candidate = tmp_path / "release-temp" / "candidate"

    create_candidate_worktree(
        repo,
        source_ref="HEAD",
        branch_name="codex/release-lock-test",
        destination=candidate,
    )
    apply_snapshot(source, candidate, report, tmp_path / "release-temp")

    assert (candidate / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"
    assert (candidate / "src" / "new.py").read_text(encoding="utf-8") == "new\n"
    assert (source / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"
    assert git_output(repo.root, "status", "--short") != ""


def test_candidate_creation_rejects_existing_branch_and_destination(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    existing_destination = tmp_path / "release-temp" / "occupied"
    existing_destination.mkdir(parents=True)

    with pytest.raises(GitError):
        create_candidate_worktree(
            repo,
            source_ref="HEAD",
            branch_name="codex/destination-must-not-create-branch",
            destination=existing_destination,
        )
    assert (
        run_test_git(
            repo.root,
            "branch",
            "--list",
            "codex/destination-must-not-create-branch",
        )
        == ""
    )

    run_test_git(repo.root, "branch", "codex/already-exists", "HEAD")
    available_destination = tmp_path / "release-temp" / "available"
    with pytest.raises(GitError):
        create_candidate_worktree(
            repo,
            source_ref="HEAD",
            branch_name="codex/already-exists",
            destination=available_destination,
        )
    assert not available_destination.exists()


def test_overlay_removes_included_deletion_and_excluded_tracked_file(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    (source / "src" / "removed.py").write_text("remove me\n", encoding="utf-8")
    (source / "src" / "private.py").write_text("exclude me\n", encoding="utf-8")
    run_test_git(source, "add", "src/removed.py", "src/private.py")
    run_test_git(source, "commit", "-m", "overlay fixture")
    (source / "src" / "nova.py").write_text("release copy\n", encoding="utf-8")
    (source / "src" / "removed.py").unlink()
    report = SnapshotReport(
        schema_version="1.0",
        decisions=[
            SnapshotDecision(
                "src/nova.py", SnapshotClass.INCLUDE, "test_include", tracked=True
            ),
            SnapshotDecision(
                "src/removed.py",
                SnapshotClass.INCLUDE,
                "test_include",
                tracked=True,
                change="deleted",
            ),
            SnapshotDecision(
                "src/private.py", SnapshotClass.EXCLUDE, "test_exclude", tracked=True
            ),
        ],
    )
    candidate = tmp_path / "release-temp" / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/overlay", candidate)

    apply_snapshot(source, candidate, report, tmp_path / "release-temp")
    commit_id = commit_candidate(candidate, "release snapshot")

    assert run_test_git(candidate, "log", "-1", "--format=%s") == "release snapshot"
    assert run_test_git(candidate, "rev-parse", "HEAD") == commit_id
    assert run_test_git(candidate, "ls-tree", "-r", "--name-only", "HEAD") == "src/nova.py"
    assert run_test_git(candidate, "show", "HEAD:src/nova.py") == "release copy"
    assert run_test_git(source, "rev-parse", "HEAD") != commit_id
    assert (source / "src" / "private.py").read_text(encoding="utf-8") == "exclude me\n"


def test_apply_snapshot_rejects_escape_and_ambiguity(tmp_path: Path) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "temp" / "candidate"
    source.mkdir()
    candidate.mkdir(parents=True)

    escape = SnapshotReport(
        schema_version="1.0",
        decisions=[
            SnapshotDecision("../private.txt", SnapshotClass.INCLUDE, "invalid_test_path")
        ],
    )
    with pytest.raises(ReleasePathError):
        apply_snapshot(source, candidate, escape, tmp_path / "temp")

    report = SnapshotReport(
        schema_version="1.0",
        decisions=[SnapshotDecision("mystery.bin", SnapshotClass.AMBIGUOUS, "binary")],
    )
    with pytest.raises(AmbiguousSnapshotError):
        apply_snapshot(source, candidate, report, tmp_path / "temp")


def test_apply_snapshot_rejects_source_links(tmp_path: Path) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "temp" / "candidate"
    source.mkdir()
    candidate.mkdir(parents=True)
    external = tmp_path / "external.txt"
    external.write_text("private\n", encoding="utf-8")
    linked = source / "linked.txt"
    try:
        linked.symlink_to(external)
    except (NotImplementedError, OSError) as error:
        if os.name != "nt":
            pytest.skip(f"file symlinks are not supported for this test user: {error}")
        external_directory = tmp_path / "external"
        external_directory.mkdir()
        (external_directory / "private.txt").write_text("private\n", encoding="utf-8")
        linked_directory = source / "linked"
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(linked_directory), str(external_directory)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            pytest.skip(f"filesystem links are not supported: {completed.stderr}")
        linked_relative = "linked/private.txt"
    else:
        linked_relative = "linked.txt"
    report = SnapshotReport(
        schema_version="1.0",
        decisions=[
            SnapshotDecision(linked_relative, SnapshotClass.INCLUDE, "test_include")
        ],
    )

    with pytest.raises(ReleasePathError):
        apply_snapshot(source, candidate, report, tmp_path / "temp")

    assert not (candidate / linked_relative).exists()


def test_cleanup_removes_real_worktree_inside_approved_root(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    candidate = tmp_path / "release-temp" / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/cleanup", candidate)

    cleanup_worktree(repo, candidate, tmp_path / "release-temp")

    assert not candidate.exists()
    assert str(candidate.resolve()) not in run_test_git(repo.root, "worktree", "list", "--porcelain")


def test_cleanup_refuses_destination_outside_approved_root(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    with pytest.raises(ReleasePathError):
        cleanup_worktree(repo, outside, tmp_path / "release-temp")

    assert sentinel.read_text(encoding="utf-8") == "keep\n"


def test_cleanup_refuses_repository_root_home_and_empty_path(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")

    with pytest.raises(ReleasePathError):
        cleanup_worktree(repo, repo.root, tmp_path)
    with pytest.raises(ReleasePathError):
        cleanup_worktree(repo, Path.home(), Path.home().parent)
    with pytest.raises(ReleasePathError):
        cleanup_worktree(repo, "", tmp_path)

    assert (repo.root / "src" / "nova.py").read_text(encoding="utf-8") == "committed\n"


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific drive-root guard")
def test_cleanup_refuses_drive_root(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    drive_root = Path(tmp_path.anchor)

    with pytest.raises(ReleasePathError):
        cleanup_worktree(repo, drive_root, drive_root / "release-temp")
