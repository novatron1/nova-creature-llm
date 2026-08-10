import os
import subprocess
from pathlib import Path

import pytest

import nova_release_worktree as worktree_module
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


def make_directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            pytest.skip(f"junction creation is not supported: {completed.stderr}")
    else:
        link.symlink_to(target, target_is_directory=True)


def remove_directory_link(link: Path) -> None:
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink()


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


def test_repository_discovery_from_real_linked_worktree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    linked = tmp_path / "linked"
    run_test_git(repo.root, "worktree", "add", "-b", "codex/discovery", str(linked), "HEAD")

    discovered = GitRepository.discover(linked / "src")

    assert discovered.root == linked.resolve()
    assert discovered.common_dir == repo.common_dir


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


def test_git_output_distinguishes_redacted_timeout_and_unavailable_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = str(tmp_path / "private-command-path")

    def timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(["git", secret], 60, stderr=secret)

    monkeypatch.setattr(worktree_module.subprocess, "run", timeout)
    with pytest.raises(GitError, match="timed out") as timed_out:
        git_output(tmp_path, "show", secret)
    assert secret not in str(timed_out.value)
    assert timed_out.value.__cause__ is None

    def unavailable(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(secret)

    monkeypatch.setattr(worktree_module.subprocess, "run", unavailable)
    with pytest.raises(GitError, match="unavailable") as missing:
        git_output(tmp_path, "status", secret)
    assert secret not in str(missing.value)
    assert missing.value.__cause__ is None


def test_candidate_overlay_preserves_source_worktree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    (source / "src" / "nova.py").write_text("working copy\n", encoding="utf-8")
    (source / "src" / "new.py").write_text("new\n", encoding="utf-8")
    report = report_for(source, include=["src/nova.py", "src/new.py"])
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"

    create_candidate_worktree(
        repo,
        source_ref="HEAD",
        branch_name="codex/release-lock-test",
        destination=candidate,
        approved_temp_root=temp_root,
    )
    apply_snapshot(source, candidate, report, temp_root)

    assert (candidate / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"
    assert (candidate / "src" / "new.py").read_text(encoding="utf-8") == "new\n"
    assert (source / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"
    assert git_output(repo.root, "status", "--short") != ""


def test_candidate_creation_rejects_existing_branch_and_destination(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    existing_destination = temp_root / "occupied"
    existing_destination.mkdir()

    with pytest.raises(GitError):
        create_candidate_worktree(
            repo,
            source_ref="HEAD",
            branch_name="codex/destination-must-not-create-branch",
            destination=existing_destination,
            approved_temp_root=temp_root,
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
    available_destination = temp_root / "available"
    with pytest.raises(GitError):
        create_candidate_worktree(
            repo,
            source_ref="HEAD",
            branch_name="codex/already-exists",
            destination=available_destination,
            approved_temp_root=temp_root,
        )
    assert not available_destination.exists()


def test_candidate_creation_requires_external_verified_temp_root(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    inside_repo = repo.root / "release-temp"
    inside_repo.mkdir()
    outside_root = tmp_path / "release-temp"
    outside_root.mkdir()

    unsafe_cases = [
        (inside_repo / "candidate", inside_repo),
        (tmp_path / "not-under-root", outside_root),
        (Path.home() / "nova-release-candidate-test", Path.home()),
        (tmp_path / "drive-root-candidate", Path(tmp_path.anchor)),
    ]
    for index, (destination, approved_root) in enumerate(unsafe_cases):
        branch = f"codex/unsafe-root-{index}"
        with pytest.raises(ReleasePathError):
            create_candidate_worktree(
                repo,
                "HEAD",
                branch,
                destination,
                approved_root,
            )
        assert run_test_git(repo.root, "branch", "--list", branch) == ""


def test_candidate_creation_rejects_linked_temp_root(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_root = tmp_path / "linked-release-temp"
    make_directory_link(linked_root, outside)

    with pytest.raises(ReleasePathError):
        create_candidate_worktree(
            repo,
            "HEAD",
            "codex/linked-root",
            linked_root / "candidate",
            linked_root,
        )

    assert not (outside / "candidate").exists()
    assert run_test_git(repo.root, "branch", "--list", "codex/linked-root") == ""


def test_candidate_creation_rejects_temp_root_below_linked_intermediate(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path / "repo")
    outside = tmp_path / "outside"
    (outside / "release-temp").mkdir(parents=True)
    linked_parent = tmp_path / "linked-parent"
    make_directory_link(linked_parent, outside)
    linked_root = linked_parent / "release-temp"

    with pytest.raises(ReleasePathError):
        create_candidate_worktree(
            repo,
            "HEAD",
            "codex/linked-intermediate",
            linked_root / "candidate",
            linked_root,
        )

    assert not (outside / "release-temp" / "candidate").exists()


def test_candidate_creation_rolls_back_branch_when_worktree_add_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    real_run_git = worktree_module._run_git
    injected = False

    def fail_first_worktree_add(root: Path, *args: str):
        nonlocal injected
        if args[:2] == ("worktree", "add") and not injected:
            injected = True
            return subprocess.CompletedProcess(
                ["git", *args],
                returncode=1,
                stdout="",
                stderr="injected worktree add failure",
            )
        return real_run_git(root, *args)

    monkeypatch.setattr(worktree_module, "_run_git", fail_first_worktree_add)
    with pytest.raises(GitError):
        create_candidate_worktree(
            repo,
            "HEAD",
            "codex/retryable",
            candidate,
            temp_root,
        )

    assert run_test_git(repo.root, "branch", "--list", "codex/retryable") == ""
    create_candidate_worktree(
        repo,
        "HEAD",
        "codex/retryable",
        candidate,
        temp_root,
    )
    assert run_test_git(candidate, "branch", "--show-current") == "codex/retryable"


def test_candidate_creation_detects_temp_root_substitution_without_writing_outside(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside\n", encoding="utf-8")
    parked = tmp_path / "parked-temp"
    candidate = temp_root / "candidate"
    real_create = getattr(worktree_module, "_create_worktree_in_root", None)
    attempted = False

    def substitute_then_create(*args: object, **kwargs: object):
        nonlocal attempted
        attempted = True
        try:
            os.replace(temp_root, parked)
            make_directory_link(temp_root, outside)
        except OSError:
            pass
        assert real_create is not None
        return real_create(*args, **kwargs)

    monkeypatch.setattr(
        worktree_module,
        "_create_worktree_in_root",
        substitute_then_create,
        raising=False,
    )
    try:
        try:
            create_candidate_worktree(
                repo,
                "HEAD",
                "codex/substitution",
                candidate,
                temp_root,
            )
        except ReleasePathError:
            pass
        assert attempted
        assert sentinel.read_text(encoding="utf-8") == "outside\n"
        assert not (outside / "candidate").exists()
    finally:
        if os.path.lexists(temp_root) and parked.exists():
            remove_directory_link(temp_root)
            os.replace(parked, temp_root)


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
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/overlay", candidate, temp_root)

    apply_snapshot(source, candidate, report, temp_root)
    commit_id = commit_candidate(candidate, "release snapshot")

    assert run_test_git(candidate, "log", "-1", "--format=%s") == "release snapshot"
    assert run_test_git(candidate, "rev-parse", "HEAD") == commit_id
    assert run_test_git(candidate, "ls-tree", "-r", "--name-only", "HEAD") == "src/nova.py"
    assert run_test_git(candidate, "show", "HEAD:src/nova.py") == "release copy"
    assert run_test_git(source, "rev-parse", "HEAD") != commit_id
    assert (source / "src" / "private.py").read_text(encoding="utf-8") == "exclude me\n"


def test_staged_deletion_is_removed_even_after_leaving_the_index(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    run_test_git(source, "rm", "src/nova.py")
    assert "src/nova.py" not in list_tracked_paths(source)
    assert list_deleted_paths(source) == ["src/nova.py"]
    report = SnapshotReport(
        "1.0",
        [
            SnapshotDecision(
                "src/nova.py",
                SnapshotClass.INCLUDE,
                "test_include",
                tracked=False,
                change="deleted",
            )
        ],
    )
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/staged-delete", candidate, temp_root)

    apply_snapshot(source, candidate, report, temp_root)

    assert not (candidate / "src" / "nova.py").exists()


def test_staged_excluded_deletion_is_removed_when_reported_untracked(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    run_test_git(source, "rm", "src/nova.py")
    report = SnapshotReport(
        "1.0",
        [
            SnapshotDecision(
                "src/nova.py",
                SnapshotClass.EXCLUDE,
                "exclude",
                tracked=False,
                change="deleted",
            )
        ],
    )
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/excluded-delete", candidate, temp_root)

    apply_snapshot(source, candidate, report, temp_root)

    assert not (candidate / "src" / "nova.py").exists()


def test_untracked_ancestor_exclusion_removes_baseline_tree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    report = SnapshotReport(
        "1.0",
        [SnapshotDecision("src", SnapshotClass.EXCLUDE, "exclude", tracked=False)],
    )
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/untracked-exclude", candidate, temp_root)

    apply_snapshot(source, candidate, report, temp_root)

    assert not (candidate / "src").exists()


def test_exclusion_wins_for_normalized_duplicate_and_ancestor(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    (source / "src" / "child.py").write_text("child release\n", encoding="utf-8")
    run_test_git(source, "add", "src/child.py")
    run_test_git(source, "commit", "-m", "precedence fixture")
    (source / "src" / "nova.py").write_text("should not copy\n", encoding="utf-8")
    report = SnapshotReport(
        "1.0",
        [
            SnapshotDecision("src\\nova.py", SnapshotClass.INCLUDE, "include", tracked=True),
            SnapshotDecision("src/nova.py", SnapshotClass.EXCLUDE, "exclude", tracked=True),
            SnapshotDecision("src", SnapshotClass.EXCLUDE, "exclude", tracked=True),
            SnapshotDecision("src/child.py", SnapshotClass.INCLUDE, "include", tracked=True),
        ],
    )
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/precedence", candidate, temp_root)

    apply_snapshot(source, candidate, report, temp_root)

    assert not (candidate / "src").exists()


def test_descendant_exclusion_removes_conflicting_included_ancestor_file(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    (source / "bundle").write_text("base bundle\n", encoding="utf-8")
    run_test_git(source, "add", "bundle")
    run_test_git(source, "commit", "-m", "descendant precedence fixture")
    (source / "bundle").write_text("release bundle\n", encoding="utf-8")
    report = SnapshotReport(
        "1.0",
        [
            SnapshotDecision("bundle", SnapshotClass.INCLUDE, "include", tracked=True),
            SnapshotDecision(
                "bundle/private.txt", SnapshotClass.EXCLUDE, "exclude", tracked=True
            ),
        ],
    )
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/descendant-exclude", candidate, temp_root)

    apply_snapshot(source, candidate, report, temp_root)

    assert not (candidate / "bundle").exists()


def test_overlay_preflights_file_directory_transitions_before_mutating(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    (source / "src" / "nova.py").write_text("new nova\n", encoding="utf-8")
    invalid_directory = source / "invalid-directory"
    invalid_directory.mkdir()
    report = SnapshotReport(
        "1.0",
        [
            SnapshotDecision("src/nova.py", SnapshotClass.INCLUDE, "include", tracked=True),
            SnapshotDecision("invalid-directory", SnapshotClass.INCLUDE, "include"),
        ],
    )
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/preflight", candidate, temp_root)

    with pytest.raises(ReleasePathError):
        apply_snapshot(source, candidate, report, temp_root)

    assert (candidate / "src" / "nova.py").read_text(encoding="utf-8") == "committed\n"


def test_overlay_preflights_nested_link_before_any_mutation(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    removal = source / "remove"
    removal.mkdir()
    (removal / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    run_test_git(source, "add", "remove/baseline.txt")
    run_test_git(source, "commit", "-m", "nested removal fixture")
    (source / "src" / "nova.py").write_text("release\n", encoding="utf-8")
    report = SnapshotReport(
        "1.0",
        [
            SnapshotDecision("src/nova.py", SnapshotClass.INCLUDE, "include", tracked=True),
            SnapshotDecision("remove", SnapshotClass.EXCLUDE, "exclude", tracked=False),
        ],
    )
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/nested-preflight", candidate, temp_root)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside\n", encoding="utf-8")
    make_directory_link(candidate / "remove" / "linked", outside)

    with pytest.raises(ReleasePathError):
        apply_snapshot(source, candidate, report, temp_root)

    assert (candidate / "src" / "nova.py").read_text(encoding="utf-8") == "committed\n"
    assert (candidate / "remove" / "baseline.txt").read_text(encoding="utf-8") == "baseline\n"
    assert sentinel.read_text(encoding="utf-8") == "outside\n"


def test_overlay_applies_directory_file_transitions_as_exact_tree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    (source / "to_file").mkdir()
    (source / "to_file" / "old.txt").write_text("old\n", encoding="utf-8")
    (source / "to_dir").write_text("old file\n", encoding="utf-8")
    run_test_git(source, "add", "to_file/old.txt", "to_dir")
    run_test_git(source, "commit", "-m", "type fixture")
    (source / "to_file" / "old.txt").unlink()
    (source / "to_file").rmdir()
    (source / "to_file").write_text("new file\n", encoding="utf-8")
    (source / "to_dir").unlink()
    (source / "to_dir").mkdir()
    (source / "to_dir" / "child.txt").write_text("new child\n", encoding="utf-8")
    report = SnapshotReport(
        "1.0",
        [
            SnapshotDecision("to_file", SnapshotClass.INCLUDE, "include"),
            SnapshotDecision("to_file/old.txt", SnapshotClass.INCLUDE, "include", change="deleted"),
            SnapshotDecision("to_dir", SnapshotClass.INCLUDE, "include", change="deleted"),
            SnapshotDecision("to_dir/child.txt", SnapshotClass.INCLUDE, "include"),
        ],
    )
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/types", candidate, temp_root)

    apply_snapshot(source, candidate, report, temp_root)

    assert (candidate / "to_file").read_text(encoding="utf-8") == "new file\n"
    assert (candidate / "to_dir" / "child.txt").read_text(encoding="utf-8") == "new child\n"
    assert sorted(
        path.relative_to(candidate).as_posix()
        for path in candidate.rglob("*")
        if path.name != ".git"
    ) == ["src", "src/nova.py", "to_dir", "to_dir/child.txt", "to_file"]


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


@pytest.mark.parametrize(
    "alias",
    [".git/HEAD", ".GIT/config", ".git::$DATA", ".git./config"],
)
def test_apply_snapshot_rejects_git_metadata_aliases(
    tmp_path: Path,
    alias: str,
) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "temp" / "candidate"
    source.mkdir()
    candidate.mkdir(parents=True)
    report = SnapshotReport(
        "1.0",
        [SnapshotDecision(alias, SnapshotClass.INCLUDE, "malicious")],
    )

    with pytest.raises(ReleasePathError):
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


def test_apply_snapshot_rejects_link_in_excluded_source_path(tmp_path: Path) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "temp" / "candidate"
    outside = tmp_path / "outside"
    source.mkdir()
    candidate.mkdir(parents=True)
    outside.mkdir()
    (outside / "private.txt").write_text("outside\n", encoding="utf-8")
    make_directory_link(source / "linked", outside)
    report = SnapshotReport(
        "1.0",
        [SnapshotDecision("linked", SnapshotClass.EXCLUDE, "exclude")],
    )

    with pytest.raises(ReleasePathError):
        apply_snapshot(source, candidate, report, tmp_path / "temp")

    assert (outside / "private.txt").read_text(encoding="utf-8") == "outside\n"


def test_apply_snapshot_rejects_source_root_below_linked_intermediate(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    source_target = outside / "source"
    source_target.mkdir(parents=True)
    (source_target / "private.txt").write_text("outside\n", encoding="utf-8")
    linked_parent = tmp_path / "linked-parent"
    make_directory_link(linked_parent, outside)
    source = linked_parent / "source"
    candidate = tmp_path / "temp" / "candidate"
    candidate.mkdir(parents=True)
    report = SnapshotReport(
        "1.0",
        [SnapshotDecision("private.txt", SnapshotClass.INCLUDE, "include")],
    )

    with pytest.raises(ReleasePathError):
        apply_snapshot(source, candidate, report, tmp_path / "temp")

    assert not (candidate / "private.txt").exists()


def test_apply_snapshot_rejects_candidate_link_without_writing_outside(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "temp" / "candidate"
    outside = tmp_path / "outside"
    (source / "linked").mkdir(parents=True)
    candidate.mkdir(parents=True)
    outside.mkdir()
    (source / "linked" / "release.txt").write_text("release\n", encoding="utf-8")
    sentinel = outside / "release.txt"
    sentinel.write_text("outside\n", encoding="utf-8")
    make_directory_link(candidate / "linked", outside)
    report = SnapshotReport(
        "1.0",
        [SnapshotDecision("linked/release.txt", SnapshotClass.INCLUDE, "include")],
    )

    with pytest.raises(ReleasePathError):
        apply_snapshot(source, candidate, report, tmp_path / "temp")

    assert sentinel.read_text(encoding="utf-8") == "outside\n"


@pytest.mark.parametrize("substitute", ["source", "candidate"])
def test_apply_snapshot_detects_intermediate_substitution_without_crossing_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substitute: str,
) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "temp" / "candidate"
    outside = tmp_path / "outside"
    (source / "src").mkdir(parents=True)
    (candidate / "src").mkdir(parents=True)
    outside.mkdir()
    (source / "src" / "nova.py").write_text("trusted\n", encoding="utf-8")
    (candidate / "src" / "nova.py").write_text("committed\n", encoding="utf-8")
    (outside / "nova.py").write_text("outside\n", encoding="utf-8")
    report = SnapshotReport(
        "1.0",
        [SnapshotDecision("src/nova.py", SnapshotClass.INCLUDE, "include")],
    )
    root = source if substitute == "source" else candidate
    intermediate = root / "src"
    parked = root / "parked-src"
    real_apply = getattr(worktree_module, "_apply_mutation_plan", None)
    attempted = False

    def substitute_then_apply(*args: object, **kwargs: object):
        nonlocal attempted
        attempted = True
        try:
            os.replace(intermediate, parked)
            make_directory_link(intermediate, outside)
        except OSError:
            pass
        assert real_apply is not None
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(
        worktree_module,
        "_apply_mutation_plan",
        substitute_then_apply,
        raising=False,
    )
    try:
        try:
            apply_snapshot(source, candidate, report, tmp_path / "temp")
        except ReleasePathError:
            pass
        assert attempted
        assert (outside / "nova.py").read_text(encoding="utf-8") == "outside\n"
        observed = parked / "nova.py" if parked.exists() else candidate / "src" / "nova.py"
        assert observed.read_text(encoding="utf-8") != "outside\n"
    finally:
        if os.path.lexists(intermediate) and parked.exists():
            remove_directory_link(intermediate)
            os.replace(parked, intermediate)


def test_apply_snapshot_rejects_source_file_replacement_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "temp" / "candidate"
    source.mkdir()
    candidate.mkdir(parents=True)
    source_file = source / "nova.py"
    source_file.write_text("trusted\n", encoding="utf-8")
    candidate_file = candidate / "nova.py"
    candidate_file.write_text("committed\n", encoding="utf-8")
    parked = source / "parked.py"
    replacement = source / "replacement.py"
    replacement.write_text("outside substitute\n", encoding="utf-8")
    report = SnapshotReport(
        "1.0",
        [SnapshotDecision("nova.py", SnapshotClass.INCLUDE, "include")],
    )
    real_read = worktree_module.os.read
    substituted = False
    substitution_blocked = False

    def replace_during_read(descriptor: int, size: int) -> bytes:
        nonlocal substituted, substitution_blocked
        if not substituted:
            substituted = True
            try:
                os.replace(source_file, parked)
                os.replace(replacement, source_file)
            except OSError:
                substitution_blocked = True
        return real_read(descriptor, size)

    monkeypatch.setattr(worktree_module.os, "read", replace_during_read)
    try:
        try:
            apply_snapshot(source, candidate, report, tmp_path / "temp")
        except ReleasePathError:
            pass
        assert substituted
        if substitution_blocked:
            assert candidate_file.read_text(encoding="utf-8") == "trusted\n"
        else:
            assert candidate_file.read_text(encoding="utf-8") == "committed\n"
    finally:
        if parked.exists():
            source_file.unlink(missing_ok=True)
            os.replace(parked, source_file)


def test_apply_snapshot_rejects_candidate_regular_file_swap_before_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "temp" / "candidate"
    source.mkdir()
    candidate.mkdir(parents=True)
    (source / "nova.py").write_text("release\n", encoding="utf-8")
    candidate_file = candidate / "nova.py"
    candidate_file.write_text("committed\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    replacement = candidate / "replacement.txt"
    os.link(outside, replacement)
    report = SnapshotReport(
        "1.0",
        [SnapshotDecision("nova.py", SnapshotClass.INCLUDE, "include")],
    )
    real_metadata = worktree_module._set_temp_metadata
    attempted = False

    def swap_candidate_then_set_metadata(*args: object, **kwargs: object) -> None:
        nonlocal attempted
        if not attempted:
            attempted = True
            os.replace(replacement, candidate_file)
        real_metadata(*args, **kwargs)

    monkeypatch.setattr(worktree_module, "_set_temp_metadata", swap_candidate_then_set_metadata)

    with pytest.raises(ReleasePathError):
        apply_snapshot(source, candidate, report, tmp_path / "temp")

    assert attempted
    assert outside.read_text(encoding="utf-8") == "outside\n"


@pytest.mark.skipif(os.name != "nt", reason="Windows descriptor metadata coverage")
def test_windows_metadata_keeps_temp_entry_pinned_until_applied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "temp" / "candidate"
    source.mkdir()
    candidate.mkdir(parents=True)
    (source / "nova.py").write_text("release\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    report = SnapshotReport(
        "1.0",
        [SnapshotDecision("nova.py", SnapshotClass.INCLUDE, "include")],
    )
    real_metadata = worktree_module._set_temp_metadata
    attempted = False
    substitution_blocked = False

    def substitute_temp_then_set_metadata(
        parent: object,
        name: str,
        source_stat: os.stat_result,
        descriptor: int,
    ) -> None:
        nonlocal attempted, substitution_blocked
        attempted = True
        temporary = parent.path / name
        parked = candidate / "parked.tmp"
        try:
            os.replace(temporary, parked)
        except OSError:
            substitution_blocked = True
        real_metadata(parent, name, source_stat, descriptor)

    monkeypatch.setattr(worktree_module, "_set_temp_metadata", substitute_temp_then_set_metadata)
    try:
        try:
            apply_snapshot(source, candidate, report, tmp_path / "temp")
        except (OSError, ReleasePathError):
            pass
        assert attempted
        assert substitution_blocked
        assert outside.read_text(encoding="utf-8") == "outside\n"
    finally:
        (candidate / "parked.tmp").unlink(missing_ok=True)


def test_cleanup_removes_real_worktree_inside_approved_root(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/cleanup", candidate, temp_root)

    cleanup_worktree(repo, candidate, temp_root)

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


def test_cleanup_refuses_unregistered_directory_without_mutating_content(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    candidate = temp_root / "not-a-worktree"
    candidate.mkdir(parents=True)
    sentinel = candidate / "sentinel.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    with pytest.raises(GitError, match="registered"):
        cleanup_worktree(repo, candidate, temp_root)

    assert sentinel.read_text(encoding="utf-8") == "keep\n"


def test_cleanup_preflights_nested_link_without_mutating_candidate(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/cleanup-nested-link", candidate, temp_root)
    kept = candidate / "kept.txt"
    kept.write_text("keep\n", encoding="utf-8")
    nested = candidate / "nested"
    nested.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside\n", encoding="utf-8")
    make_directory_link(nested / "linked", outside)

    with pytest.raises(ReleasePathError, match="link"):
        cleanup_worktree(repo, candidate, temp_root)

    assert kept.read_text(encoding="utf-8") == "keep\n"
    assert sentinel.read_text(encoding="utf-8") == "outside\n"
    assert worktree_module._worktree_is_registered(repo, candidate)


def test_cleanup_git_preflight_failure_leaves_content_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/cleanup-preflight-fail", candidate, temp_root)
    sentinel = candidate / "sentinel.txt"
    sentinel.write_text("keep\n", encoding="utf-8")
    real_run_git = worktree_module._run_git

    def fail_worktree_list(root: Path, *args: str):
        if args[:2] == ("worktree", "list"):
            return subprocess.CompletedProcess(
                ["git", *args], returncode=1, stdout="", stderr="injected list failure"
            )
        return real_run_git(root, *args)

    monkeypatch.setattr(worktree_module, "_run_git", fail_worktree_list)

    with pytest.raises(GitError):
        cleanup_worktree(repo, candidate, temp_root)

    assert sentinel.read_text(encoding="utf-8") == "keep\n"


def test_cleanup_unregister_failure_restores_all_candidate_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/cleanup-remove-fail", candidate, temp_root)
    sentinel = candidate / "sentinel.txt"
    sentinel.write_text("keep\n", encoding="utf-8")
    git_pointer = (candidate / ".git").read_text(encoding="utf-8")
    real_run_git = worktree_module._run_git

    def fail_worktree_remove(root: Path, *args: str):
        if args[:2] == ("worktree", "remove"):
            return subprocess.CompletedProcess(
                ["git", *args], returncode=1, stdout="", stderr="injected remove failure"
            )
        return real_run_git(root, *args)

    monkeypatch.setattr(worktree_module, "_run_git", fail_worktree_remove)

    with pytest.raises(GitError):
        cleanup_worktree(repo, candidate, temp_root)

    assert sentinel.read_text(encoding="utf-8") == "keep\n"
    assert (candidate / ".git").read_text(encoding="utf-8") == git_pointer
    registered = {
        Path(line.removeprefix("worktree ")).resolve()
        for line in run_test_git(repo.root, "worktree", "list", "--porcelain").splitlines()
        if line.startswith("worktree ")
    }
    assert candidate.resolve() in registered


def test_cleanup_placeholder_setup_failure_restores_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/cleanup-setup-fail", candidate, temp_root)
    sentinel = candidate / "sentinel.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    def fail_placeholder_write(*args: object, **kwargs: object) -> None:
        raise OSError("injected placeholder write failure")

    monkeypatch.setattr(
        worktree_module,
        "_write_anchored_regular_file",
        fail_placeholder_write,
    )

    with pytest.raises(OSError, match="placeholder write"):
        cleanup_worktree(repo, candidate, temp_root)

    assert sentinel.read_text(encoding="utf-8") == "keep\n"
    assert not any(temp_root.glob(".nova-release-cleanup-*"))


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


def test_cleanup_detects_candidate_substitution_without_deleting_outside(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/cleanup-substitute", candidate, temp_root)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside\n", encoding="utf-8")
    parked = temp_root / "parked-candidate"
    real_remove = getattr(worktree_module, "_remove_candidate_tree_anchored", None)
    attempted = False

    def substitute_then_remove(*args: object, **kwargs: object):
        nonlocal attempted
        attempted = True
        try:
            os.replace(candidate, parked)
            make_directory_link(candidate, outside)
        except OSError:
            pass
        assert real_remove is not None
        return real_remove(*args, **kwargs)

    monkeypatch.setattr(
        worktree_module,
        "_remove_candidate_tree_anchored",
        substitute_then_remove,
        raising=False,
    )
    try:
        try:
            cleanup_worktree(repo, candidate, temp_root)
        except ReleasePathError:
            pass
        assert attempted
        assert sentinel.read_text(encoding="utf-8") == "outside\n"
    finally:
        if os.path.lexists(candidate) and parked.exists():
            remove_directory_link(candidate)
            os.replace(parked, candidate)


def test_cleanup_locks_candidate_during_git_unregister(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo(tmp_path / "repo")
    temp_root = tmp_path / "release-temp"
    temp_root.mkdir()
    candidate = temp_root / "candidate"
    create_candidate_worktree(repo, "HEAD", "codex/cleanup-git-lock", candidate, temp_root)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside\n", encoding="utf-8")
    parked = temp_root / "parked-candidate"
    real_run_git = worktree_module._run_git
    attempted = False
    substitution_blocked = False

    def substitute_during_unregister(root: Path, *args: str):
        nonlocal attempted, substitution_blocked
        if args[:2] == ("worktree", "remove"):
            attempted = True
            try:
                os.replace(candidate, parked)
                make_directory_link(candidate, outside)
            except OSError:
                substitution_blocked = True
        return real_run_git(root, *args)

    monkeypatch.setattr(worktree_module, "_run_git", substitute_during_unregister)
    try:
        cleanup_worktree(repo, candidate, temp_root)
        assert attempted
        assert substitution_blocked
        assert sentinel.read_text(encoding="utf-8") == "outside\n"
        assert not candidate.exists()
    finally:
        if os.path.lexists(candidate) and parked.exists():
            remove_directory_link(candidate)
            os.replace(parked, candidate)
