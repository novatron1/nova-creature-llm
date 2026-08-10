"""Guarded Git worktrees and fail-closed release snapshot overlays."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from nova_release_policy import SnapshotClass, SnapshotDecision, SnapshotReport


class GitError(RuntimeError):
    """Raised when a Git command or repository operation fails."""


class ReleasePathError(ValueError):
    """Raised when a release path crosses an approved filesystem boundary."""


class AmbiguousSnapshotError(ValueError):
    """Raised when a snapshot report contains unresolved decisions."""


_GIT_TIMEOUT_SECONDS = 60
_MAX_GIT_STDERR = 2_000


def _redacted_stderr(root: Path, args: tuple[str, ...], stderr: str) -> str:
    redacted = stderr.strip() or "Git returned no diagnostic output."
    sensitive_values = {
        str(root),
        str(root.resolve()),
        str(Path.home()),
        *(argument for argument in args if argument),
    }
    for value in sorted(sensitive_values, key=len, reverse=True):
        redacted = redacted.replace(value, "<redacted>")
        redacted = redacted.replace(value.replace("\\", "/"), "<redacted>")
    if len(redacted) > _MAX_GIT_STDERR:
        redacted = f"{redacted[:_MAX_GIT_STDERR]}..."
    return redacted


def _run_git(root: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
    git_root = Path(root)
    try:
        return subprocess.run(
            ["git", "-C", str(git_root), *args],
            shell=False,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitError("Git command could not be completed.") from error


def git_output(root: str | Path, *args: str) -> str:
    """Run Git without a shell and return its stripped standard output."""

    git_root = Path(root)
    completed = _run_git(git_root, *args)
    if completed.returncode != 0:
        diagnostic = _redacted_stderr(git_root, args, completed.stderr)
        raise GitError(f"Git command failed with exit code {completed.returncode}: {diagnostic}")
    return completed.stdout.strip()


@dataclass(frozen=True)
class GitRepository:
    root: Path
    common_dir: Path

    @classmethod
    def discover(cls, root: str | Path) -> "GitRepository":
        resolved = Path(root).resolve()
        top = Path(git_output(resolved, "rev-parse", "--show-toplevel")).resolve()
        common = Path(git_output(top, "rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = (top / common).resolve()
        return cls(root=top, common_dir=common)


def _nul_paths(output: str) -> list[str]:
    return sorted(path for path in output.split("\0") if path)


def list_tracked_paths(root: str | Path) -> list[str]:
    """Return the index's tracked paths in deterministic order."""

    return _nul_paths(git_output(root, "ls-files", "-z"))


def list_deleted_paths(root: str | Path) -> list[str]:
    """Return tracked paths deleted from the index or working tree versus HEAD."""

    return _nul_paths(
        git_output(root, "diff", "--name-only", "--diff-filter=D", "-z", "HEAD", "--")
    )


def _is_link_or_reparse(path: Path) -> bool:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    return bool(reparse_flag and file_attributes & reparse_flag)


def _existing_path_has_link(path: Path) -> bool:
    absolute = path.absolute()
    current = Path(absolute.anchor) if absolute.anchor else Path()
    start_index = 1 if absolute.anchor else 0
    for part in absolute.parts[start_index:]:
        current /= part
        if not os.path.lexists(current):
            break
        if _is_link_or_reparse(current):
            return True
    return False


def _resolved_input(path: str | Path, label: str) -> Path:
    raw = os.fspath(path)
    if not raw or not raw.strip():
        raise ReleasePathError(f"{label} must not be empty")
    return Path(path).resolve()


def _is_drive_root(path: Path) -> bool:
    return bool(path.anchor) and path == Path(path.anchor)


def _strict_descendant(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return relative != Path(".")


def _safe_destination(
    path: str | Path,
    approved_temp_root: str | Path,
    repository_root: str | Path | None = None,
) -> Path:
    destination = _resolved_input(path, "destination")
    temp_root = _resolved_input(approved_temp_root, "approved temporary root")
    forbidden = {Path.home().resolve()}
    if destination.anchor:
        forbidden.add(Path(destination.anchor).resolve())
    if repository_root is not None:
        forbidden.add(_resolved_input(repository_root, "repository root"))
    if destination in forbidden or _is_drive_root(destination):
        raise ReleasePathError("destination is a protected filesystem root")
    if not _strict_descendant(destination, temp_root):
        raise ReleasePathError("destination is outside the approved temporary root")
    return destination


def _validated_root(path: str | Path, label: str) -> Path:
    unresolved = Path(path).absolute()
    resolved = _resolved_input(path, label)
    if not unresolved.is_dir():
        raise ReleasePathError(f"{label} is not an existing directory")
    if _existing_path_has_link(unresolved):
        raise ReleasePathError(f"{label} contains a filesystem link")
    return resolved


def _normalized_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:($|/)", normalized)
        or "\0" in normalized
    ):
        raise ReleasePathError("snapshot path must be workspace-relative")
    pure_path = PurePosixPath(normalized)
    if pure_path == PurePosixPath(".") or ".." in pure_path.parts:
        raise ReleasePathError("snapshot path must not escape its workspace")
    if pure_path.parts[0].lower() == ".git":
        raise ReleasePathError("snapshot path must not address Git metadata")
    return pure_path.as_posix()


def _guarded_target(candidate_root: Path, relative_path: str) -> Path:
    target = candidate_root.joinpath(*PurePosixPath(relative_path).parts)
    resolved_target = target.resolve()
    if not _strict_descendant(resolved_target, candidate_root):
        raise ReleasePathError("candidate target escapes the candidate root")
    if _existing_path_has_link(target):
        raise ReleasePathError("candidate target contains a filesystem link")
    return target


def _source_file(source_root: Path, relative_path: str) -> Path:
    source_path = source_root.joinpath(*PurePosixPath(relative_path).parts)
    resolved_source = source_path.resolve()
    if not _strict_descendant(resolved_source, source_root):
        raise ReleasePathError("source path escapes the source root")
    if _existing_path_has_link(source_path):
        raise ReleasePathError("source path contains a filesystem link")
    return source_path


def _guarded_remove(candidate_root: Path, target: Path) -> None:
    guarded = _guarded_target(candidate_root, target.relative_to(candidate_root).as_posix())
    if not os.path.lexists(guarded):
        return
    if guarded.is_dir():
        shutil.rmtree(guarded)
    else:
        guarded.unlink()


def create_candidate_worktree(
    repository: GitRepository,
    source_ref: str,
    branch_name: str,
    destination: str | Path,
) -> Path:
    """Create a new branch and linked worktree without altering the source checkout."""

    destination_path = _safe_destination(
        destination,
        Path(destination).absolute().parent,
        repository.root,
    )
    if os.path.lexists(destination_path):
        raise GitError("candidate worktree destination already exists")
    git_output(repository.root, "check-ref-format", "--branch", branch_name)
    existing_branch = git_output(
        repository.root,
        "branch",
        "--list",
        "--format=%(refname)",
        branch_name,
    )
    if existing_branch:
        raise GitError("candidate branch already exists")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    git_output(repository.root, "branch", branch_name, source_ref)
    git_output(repository.root, "worktree", "add", str(destination_path), branch_name)
    return destination_path


def _preflight_snapshot(
    source_root: Path,
    candidate_root: Path,
    report: SnapshotReport,
) -> list[tuple[SnapshotDecision, str, Path | None, Path]]:
    prepared: list[tuple[SnapshotDecision, str, Path | None, Path]] = []
    seen: set[str] = set()
    for decision in report.decisions:
        relative_path = _normalized_relative_path(decision.path)
        if relative_path in seen:
            raise ReleasePathError("snapshot report contains a duplicate path")
        seen.add(relative_path)
        candidate_path = _guarded_target(candidate_root, relative_path)
        source_path = _source_file(source_root, relative_path)
        if decision.classification is SnapshotClass.INCLUDE and decision.change != "deleted":
            if not source_path.exists() or not stat.S_ISREG(source_path.lstat().st_mode):
                raise ReleasePathError("included snapshot path is not a present regular file")
            prepared.append((decision, relative_path, source_path, candidate_path))
        else:
            prepared.append((decision, relative_path, None, candidate_path))
    return prepared


def apply_snapshot(
    source: str | Path,
    candidate: str | Path,
    report: SnapshotReport,
    approved_temp_root: str | Path,
) -> None:
    """Overlay a validated snapshot report onto an isolated candidate worktree."""

    if report.ambiguous:
        raise AmbiguousSnapshotError("snapshot report contains ambiguous decisions")
    source_root = _validated_root(source, "source root")
    candidate_root = _safe_destination(candidate, approved_temp_root, source_root)
    candidate_root = _validated_root(candidate_root, "candidate root")
    prepared = _preflight_snapshot(source_root, candidate_root, report)

    for decision, _relative_path, source_path, candidate_path in prepared:
        if decision.classification is SnapshotClass.INCLUDE and decision.change != "deleted":
            assert source_path is not None
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, candidate_path)
        elif decision.tracked and (
            decision.classification is SnapshotClass.EXCLUDE
            or (
                decision.classification is SnapshotClass.INCLUDE
                and decision.change == "deleted"
            )
        ):
            _guarded_remove(candidate_root, candidate_path)


def commit_candidate(candidate: str | Path, message: str) -> str:
    """Commit the candidate's exact overlaid filesystem state and return its commit ID."""

    candidate_root = _validated_root(candidate, "candidate root")
    git_output(candidate_root, "add", "-A")
    git_output(candidate_root, "commit", "-m", message)
    return git_output(candidate_root, "rev-parse", "HEAD")


def cleanup_worktree(
    repository: GitRepository,
    destination: str | Path,
    approved_temp_root: str | Path,
) -> None:
    """Remove a linked worktree only when it is contained by the approved temp root."""

    destination_path = _safe_destination(
        destination,
        approved_temp_root,
        repository.root,
    )
    if _existing_path_has_link(destination_path):
        raise ReleasePathError("worktree destination contains a filesystem link")
    git_output(repository.root, "worktree", "remove", "--force", str(destination_path))
    if os.path.lexists(destination_path):
        _guarded_remove(Path(approved_temp_root).resolve(), destination_path)
