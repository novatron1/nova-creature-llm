"""Guarded release worktrees for one cooperative local controller.

The controller exclusively owns each verified temporary root. Static links,
escapes, identity/type mismatches, registration mismatches, and operation
errors fail closed. POSIX directory-FD provenance remains authoritative after
opening; deliberate same-UID/root concurrent mutation of owned paths is out of
scope. Windows additionally denies delete sharing while directories are held.
"""

from __future__ import annotations

import os
import re
import secrets
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from nova_release_policy import SnapshotClass, SnapshotDecision, SnapshotReport

if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes


class GitError(RuntimeError):
    """Raised when a Git command or repository operation fails."""


class ReleasePathError(ValueError):
    """Raised when a release path crosses an approved filesystem boundary."""


class AmbiguousSnapshotError(ValueError):
    """Raised when a snapshot report contains unresolved decisions."""


_GIT_TIMEOUT_SECONDS = 60
_MAX_GIT_STDERR = 2_000
_COPY_BLOCK_SIZE = 1024 * 1024

if os.name == "nt":
    _FILE_LIST_DIRECTORY = 0x0001
    _FILE_READ_ATTRIBUTES = 0x0080
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _FILE_BASIC_INFO_CLASS = 0
    _WINDOWS_EPOCH_TICKS = 116_444_736_000_000_000

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    class _FileBasicInformation(ctypes.Structure):
        _fields_ = [
            ("CreationTime", ctypes.c_longlong),
            ("LastAccessTime", ctypes.c_longlong),
            ("LastWriteTime", ctypes.c_longlong),
            ("ChangeTime", ctypes.c_longlong),
            ("FileAttributes", wintypes.DWORD),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _create_file = _kernel32.CreateFileW
    _create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _create_file.restype = wintypes.HANDLE
    _get_file_information = _kernel32.GetFileInformationByHandle
    _get_file_information.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    ]
    _get_file_information.restype = wintypes.BOOL
    _close_handle = _kernel32.CloseHandle
    _close_handle.argtypes = [wintypes.HANDLE]
    _close_handle.restype = wintypes.BOOL
    _set_file_information = _kernel32.SetFileInformationByHandle
    _set_file_information.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _set_file_information.restype = wintypes.BOOL


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
    try:
        return subprocess.run(
            ["git", "-C", str(Path(root)), *args],
            shell=False,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise GitError("Git command timed out after 60 seconds.") from None
    except OSError:
        raise GitError("Git executable is unavailable.") from None


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
    return _nul_paths(git_output(root, "ls-files", "-z"))


def list_deleted_paths(root: str | Path) -> list[str]:
    return _nul_paths(
        git_output(root, "diff", "--name-only", "--diff-filter=D", "-z", "HEAD", "--")
    )


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    if stat.S_ISLNK(metadata.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _same_identity_and_type(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
    )


class _DirectoryAnchor:
    path: Path

    def validate_path(self) -> None:
        raise NotImplementedError

    def stat_entry(self, name: str) -> os.stat_result:
        raise NotImplementedError

    def entries(self) -> list[tuple[str, os.stat_result]]:
        raise NotImplementedError

    def open_file(self, name: str, flags: int, mode: int = 0o666) -> int:
        raise NotImplementedError

    def mkdir_entry(self, name: str) -> None:
        raise NotImplementedError

    def unlink_entry(self, name: str) -> None:
        raise NotImplementedError

    def rmdir_entry(self, name: str) -> None:
        raise NotImplementedError

    def replace_entry(self, source: str, destination: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class _PosixDirectoryAnchor(_DirectoryAnchor):
    def __init__(self, path: Path, descriptor: int, opened: os.stat_result) -> None:
        self.path = path
        self.descriptor = descriptor
        self.opened = opened

    def validate_path(self) -> None:
        current = self.path.stat(follow_symlinks=False)
        opened = os.fstat(self.descriptor)
        if (
            _is_link_or_reparse(current)
            or not stat.S_ISDIR(current.st_mode)
            or not _same_identity_and_type(self.opened, current)
            or not _same_identity_and_type(self.opened, opened)
        ):
            raise ReleasePathError("anchored directory identity changed")

    def stat_entry(self, name: str) -> os.stat_result:
        return os.stat(name, dir_fd=self.descriptor, follow_symlinks=False)

    def entries(self) -> list[tuple[str, os.stat_result]]:
        with os.scandir(self.descriptor) as iterator:
            return sorted(
                ((entry.name, entry.stat(follow_symlinks=False)) for entry in iterator),
                key=lambda item: item[0],
            )

    def open_file(self, name: str, flags: int, mode: int = 0o666) -> int:
        self.validate_path()
        return os.open(name, flags, mode, dir_fd=self.descriptor)

    def mkdir_entry(self, name: str) -> None:
        self.validate_path()
        os.mkdir(name, dir_fd=self.descriptor)

    def unlink_entry(self, name: str) -> None:
        self.validate_path()
        os.unlink(name, dir_fd=self.descriptor)

    def rmdir_entry(self, name: str) -> None:
        self.validate_path()
        os.rmdir(name, dir_fd=self.descriptor)

    def replace_entry(self, source: str, destination: str) -> None:
        self.validate_path()
        os.replace(source, destination, src_dir_fd=self.descriptor, dst_dir_fd=self.descriptor)

    def close(self) -> None:
        os.close(self.descriptor)


if os.name == "nt":

    def _windows_information(handle: int) -> _ByHandleFileInformation:
        information = _ByHandleFileInformation()
        if not _get_file_information(handle, ctypes.byref(information)):
            raise ctypes.WinError(ctypes.get_last_error())
        return information


    def _windows_index(information: _ByHandleFileInformation) -> int:
        return (information.nFileIndexHigh << 32) | information.nFileIndexLow


    class _WindowsDirectoryAnchor(_DirectoryAnchor):
        def __init__(self, path: Path, handle: int, opened: os.stat_result, index: int) -> None:
            self.path = path
            self.handle = handle
            self.opened = opened
            self.index = index

        def validate_path(self) -> None:
            current = self.path.stat(follow_symlinks=False)
            information = _windows_information(self.handle)
            if (
                _is_link_or_reparse(current)
                or not stat.S_ISDIR(current.st_mode)
                or not _same_identity_and_type(self.opened, current)
                or information.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT
                or not information.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY
                or _windows_index(information) != self.index
            ):
                raise ReleasePathError("anchored directory identity changed")

        def stat_entry(self, name: str) -> os.stat_result:
            self.validate_path()
            return (self.path / name).stat(follow_symlinks=False)

        def entries(self) -> list[tuple[str, os.stat_result]]:
            self.validate_path()
            with os.scandir(self.path) as iterator:
                return sorted(
                    (
                        (entry.name, (self.path / entry.name).stat(follow_symlinks=False))
                        for entry in iterator
                    ),
                    key=lambda item: item[0],
                )

        def open_file(self, name: str, flags: int, mode: int = 0o666) -> int:
            self.validate_path()
            return os.open(self.path / name, flags, mode)

        def mkdir_entry(self, name: str) -> None:
            self.validate_path()
            (self.path / name).mkdir()

        def unlink_entry(self, name: str) -> None:
            self.validate_path()
            (self.path / name).unlink()

        def rmdir_entry(self, name: str) -> None:
            self.validate_path()
            (self.path / name).rmdir()

        def replace_entry(self, source: str, destination: str) -> None:
            self.validate_path()
            os.replace(self.path / source, self.path / destination)

        def close(self) -> None:
            if not _close_handle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())


def _open_directory_anchor(
    path: Path,
    expected: os.stat_result | None = None,
    *,
    parent: _DirectoryAnchor | None = None,
    name: str | None = None,
) -> _DirectoryAnchor:
    if parent is not None:
        parent.validate_path()
    if os.name == "nt":
        before = path.stat(follow_symlinks=False)
        if expected is not None and not _same_identity_and_type(expected, before):
            raise ReleasePathError("directory identity changed before secure open")
        if _is_link_or_reparse(before) or not stat.S_ISDIR(before.st_mode):
            raise ReleasePathError("refusing linked or non-directory path")
        handle = _create_file(
            str(path.absolute()),
            _FILE_LIST_DIRECTORY | _FILE_READ_ATTRIBUTES,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            raise ReleasePathError("could not securely anchor directory")
        try:
            information = _windows_information(handle)
            after = path.stat(follow_symlinks=False)
            if (
                not _same_identity_and_type(before, after)
                or information.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT
                or not information.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY
                or _windows_index(information) != after.st_ino
            ):
                raise ReleasePathError("directory identity changed during secure open")
            return _WindowsDirectoryAnchor(path, handle, after, _windows_index(information))
        except BaseException:
            _close_handle(handle)
            raise

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if parent is None:
        before = path.stat(follow_symlinks=False)
        descriptor = os.open(path, flags)
    else:
        if not isinstance(parent, _PosixDirectoryAnchor) or name is None:
            raise ReleasePathError("invalid anchored parent")
        before = parent.stat_entry(name)
        descriptor = os.open(name, flags, dir_fd=parent.descriptor)
    try:
        opened = os.fstat(descriptor)
        if (
            (expected is not None and not _same_identity_and_type(expected, before))
            or _is_link_or_reparse(before)
            or not stat.S_ISDIR(before.st_mode)
            or not _same_identity_and_type(before, opened)
        ):
            raise ReleasePathError("directory identity changed during secure open")
        return _PosixDirectoryAnchor(path, descriptor, opened)
    except BaseException:
        os.close(descriptor)
        raise


def _close_anchors(anchors: list[_DirectoryAnchor]) -> None:
    first_error: BaseException | None = None
    for anchor in reversed(anchors):
        try:
            anchor.close()
        except BaseException as error:
            if first_error is None:
                first_error = error
    if first_error is not None:
        raise first_error


def _open_chain(
    root: _DirectoryAnchor,
    parts: tuple[str, ...],
    *,
    create: bool = False,
) -> list[_DirectoryAnchor]:
    anchors: list[_DirectoryAnchor] = []
    parent = root
    try:
        for name in parts:
            try:
                metadata = parent.stat_entry(name)
            except FileNotFoundError:
                if not create:
                    raise ReleasePathError("required directory is missing") from None
                parent.mkdir_entry(name)
                metadata = parent.stat_entry(name)
            if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise ReleasePathError("path component is linked or not a directory")
            child = _open_directory_anchor(
                parent.path / name,
                metadata,
                parent=parent,
                name=name,
            )
            anchors.append(child)
            parent = child
        return anchors
    except BaseException:
        _close_anchors(anchors)
        raise


def _absolute_input(path: str | Path, label: str) -> Path:
    raw = os.fspath(path)
    if not raw or not raw.strip():
        raise ReleasePathError(f"{label} must not be empty")
    return Path(path).absolute()


def _strict_descendant(path: Path, root: Path) -> bool:
    try:
        return path.relative_to(root) != Path(".")
    except ValueError:
        return False


def _protected_root(path: Path) -> bool:
    resolved = path.resolve()
    return resolved == Path.home().resolve() or (
        bool(resolved.anchor) and resolved == Path(resolved.anchor).resolve()
    )


def _verified_temp_root(
    approved_temp_root: str | Path,
    protected_root: str | Path,
) -> tuple[Path, _DirectoryAnchor]:
    raw_root = _absolute_input(approved_temp_root, "approved temporary root")
    try:
        metadata = raw_root.stat(follow_symlinks=False)
    except OSError:
        raise ReleasePathError("approved temporary root must already exist") from None
    if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise ReleasePathError("approved temporary root must be an unlinked directory")
    resolved = raw_root.resolve(strict=True)
    if resolved != raw_root or _protected_root(resolved):
        raise ReleasePathError("approved temporary root is protected or linked")
    protected = _absolute_input(protected_root, "protected root").resolve()
    if resolved == protected or _strict_descendant(resolved, protected) or _strict_descendant(protected, resolved):
        raise ReleasePathError("approved temporary root overlaps the protected repository")
    anchor = _open_directory_anchor(raw_root)
    try:
        anchor.validate_path()
    except BaseException:
        anchor.close()
        raise
    return resolved, anchor


def _safe_destination(path: str | Path, approved_temp_root: Path) -> tuple[Path, tuple[str, ...]]:
    absolute = _absolute_input(path, "destination")
    resolved = absolute.resolve()
    if _protected_root(resolved) or not _strict_descendant(resolved, approved_temp_root):
        raise ReleasePathError("destination is outside the approved temporary root")
    try:
        relative = absolute.relative_to(approved_temp_root)
    except ValueError:
        raise ReleasePathError("destination path uses a linked temporary ancestor") from None
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReleasePathError("destination is not a safe temporary child")
    return absolute, relative.parts


def _entry_or_none(anchor: _DirectoryAnchor, name: str) -> os.stat_result | None:
    try:
        return anchor.stat_entry(name)
    except FileNotFoundError:
        return None


def _destination_parent(
    temp_anchor: _DirectoryAnchor,
    relative_parts: tuple[str, ...],
    *,
    create: bool,
) -> tuple[_DirectoryAnchor, list[_DirectoryAnchor], str]:
    anchors = _open_chain(temp_anchor, relative_parts[:-1], create=create)
    parent = anchors[-1] if anchors else temp_anchor
    return parent, anchors, relative_parts[-1]


def _create_worktree_in_root(
    repository: GitRepository,
    branch_name: str,
    destination: Path,
    temp_anchor: _DirectoryAnchor,
    relative_parts: tuple[str, ...],
) -> None:
    temp_anchor.validate_path()
    parent, parents, name = _destination_parent(temp_anchor, relative_parts, create=True)
    candidate_anchor: _DirectoryAnchor | None = None
    try:
        if _entry_or_none(parent, name) is not None:
            raise GitError("candidate worktree destination already exists")
        parent.mkdir_entry(name)
        metadata = parent.stat_entry(name)
        candidate_anchor = _open_directory_anchor(
            parent.path / name,
            metadata,
            parent=parent,
            name=name,
        )
        candidate_anchor.validate_path()
        git_output(repository.root, "worktree", "add", str(destination), branch_name)
        candidate_anchor.validate_path()
        temp_anchor.validate_path()
    except BaseException:
        if candidate_anchor is not None:
            candidate_anchor.close()
            candidate_anchor = None
        try:
            metadata = _entry_or_none(parent, name)
            if metadata is not None and stat.S_ISDIR(metadata.st_mode):
                parent.rmdir_entry(name)
        except OSError:
            pass
        raise
    finally:
        if candidate_anchor is not None:
            candidate_anchor.close()
        _close_anchors(parents)


def create_candidate_worktree(
    repository: GitRepository,
    source_ref: str,
    branch_name: str,
    destination: str | Path,
    approved_temp_root: str | Path,
) -> Path:
    """Create a branch and linked worktree beneath a verified external temp root."""

    temp_root, temp_anchor = _verified_temp_root(approved_temp_root, repository.root)
    destination_path, relative_parts = _safe_destination(destination, temp_root)
    branch_created = False
    created_oid = ""
    try:
        parent, parents, name = _destination_parent(temp_anchor, relative_parts, create=False)
        try:
            if _entry_or_none(parent, name) is not None:
                raise GitError("candidate worktree destination already exists")
        finally:
            _close_anchors(parents)
        git_output(repository.root, "check-ref-format", "--branch", branch_name)
        if git_output(repository.root, "branch", "--list", "--format=%(refname)", branch_name):
            raise GitError("candidate branch already exists")
        git_output(repository.root, "branch", branch_name, source_ref)
        branch_created = True
        created_oid = git_output(repository.root, "rev-parse", branch_name)
        _create_worktree_in_root(
            repository,
            branch_name,
            destination_path,
            temp_anchor,
            relative_parts,
        )
        return destination_path
    except BaseException as original:
        if branch_created:
            try:
                current_oid = git_output(repository.root, "rev-parse", branch_name)
                if current_oid != created_oid:
                    raise GitError("candidate branch changed; automatic rollback refused")
                git_output(repository.root, "branch", "-D", branch_name)
            except BaseException:
                raise GitError("candidate creation failed and branch rollback requires recovery") from None
        raise original
    finally:
        temp_anchor.close()


def _metadata_alias(part: str) -> bool:
    win32_base = part.split(":", 1)[0].rstrip(" .").lower()
    return win32_base == ".git"


def _normalized_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:($|/)", normalized)
        or "\0" in normalized
    ):
        raise ReleasePathError("snapshot path must be workspace-relative")
    pure = PurePosixPath(normalized)
    if pure == PurePosixPath(".") or ".." in pure.parts:
        raise ReleasePathError("snapshot path must not escape its workspace")
    if any(_metadata_alias(part) for part in pure.parts):
        raise ReleasePathError("snapshot path must not address Git metadata")
    return pure.as_posix()


def _parts(path: str) -> tuple[str, ...]:
    return PurePosixPath(path).parts


def _prefix(left: str, right: str) -> bool:
    left_parts = _parts(left)
    right_parts = _parts(right)
    return len(left_parts) <= len(right_parts) and right_parts[: len(left_parts)] == left_parts


@dataclass(frozen=True)
class _CopyOperation:
    path: str
    source_stat: os.stat_result


@dataclass(frozen=True)
class _MutationPlan:
    removals: tuple[str, ...]
    copies: tuple[_CopyOperation, ...]


def _canonical_decisions(
    report: SnapshotReport,
) -> tuple[dict[str, SnapshotDecision], set[str], set[str], set[str]]:
    groups: dict[str, list[SnapshotDecision]] = {}
    for decision in report.decisions:
        groups.setdefault(_normalized_relative_path(decision.path), []).append(decision)
    exclusions = {
        path
        for path, decisions in groups.items()
        if any(item.classification is SnapshotClass.EXCLUDE for item in decisions)
    }
    copies: dict[str, SnapshotDecision] = {}
    removals: set[str] = set()
    for path, decisions in groups.items():
        if path in exclusions:
            removals.add(path)
            continue
        includes = [item for item in decisions if item.classification is SnapshotClass.INCLUDE]
        if not includes:
            continue
        if any(item.change == "deleted" for item in includes):
            removals.add(path)
        else:
            copies[path] = includes[0]
    for path in list(copies):
        if any(_prefix(excluded, path) or _prefix(path, excluded) for excluded in exclusions):
            copies.pop(path)
            removals.add(path)
    return copies, removals, exclusions, set(groups)


def _source_stat(root: _DirectoryAnchor, path: str) -> os.stat_result:
    parts = _parts(path)
    anchors = _open_chain(root, parts[:-1])
    parent = anchors[-1] if anchors else root
    try:
        metadata = parent.stat_entry(parts[-1])
        if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
            raise ReleasePathError("included snapshot path is not a regular unlinked file")
        return metadata
    finally:
        _close_anchors(anchors)


def _validate_source_path_if_present(root: _DirectoryAnchor, path: str) -> None:
    parts = _parts(path)
    parent = root
    anchors: list[_DirectoryAnchor] = []
    try:
        for index, name in enumerate(parts):
            metadata = _entry_or_none(parent, name)
            if metadata is None:
                return
            if _is_link_or_reparse(metadata):
                raise ReleasePathError("source path contains a filesystem link")
            if index == len(parts) - 1:
                if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)):
                    raise ReleasePathError("source path has an unsupported type")
                return
            if not stat.S_ISDIR(metadata.st_mode):
                return
            child = _open_directory_anchor(
                parent.path / name,
                metadata,
                parent=parent,
                name=name,
            )
            anchors.append(child)
            parent = child
    finally:
        _close_anchors(anchors)


def _inspect_candidate(
    root: _DirectoryAnchor,
    path: str,
) -> tuple[str, str | None]:
    parts = _parts(path)
    parent = root
    anchors: list[_DirectoryAnchor] = []
    try:
        for index, name in enumerate(parts):
            metadata = _entry_or_none(parent, name)
            if metadata is None:
                return "missing", None
            if _is_link_or_reparse(metadata):
                raise ReleasePathError("candidate path contains a filesystem link")
            current = PurePosixPath(*parts[: index + 1]).as_posix()
            if index == len(parts) - 1:
                if stat.S_ISDIR(metadata.st_mode):
                    return "directory", current
                if stat.S_ISREG(metadata.st_mode):
                    return "file", current
                raise ReleasePathError("candidate path has an unsupported type")
            if not stat.S_ISDIR(metadata.st_mode):
                return "ancestor_file", current
            child = _open_directory_anchor(
                parent.path / name,
                metadata,
                parent=parent,
                name=name,
            )
            anchors.append(child)
            parent = child
        raise AssertionError("unreachable")
    finally:
        _close_anchors(anchors)


def _build_mutation_plan(
    source_root: _DirectoryAnchor,
    candidate_root: _DirectoryAnchor,
    report: SnapshotReport,
) -> _MutationPlan:
    copies, removals, _exclusions, all_paths = _canonical_decisions(report)
    for path in sorted(all_paths):
        _validate_source_path_if_present(source_root, path)
        _inspect_candidate(candidate_root, path)
    copy_paths = sorted(copies)
    for index, left in enumerate(copy_paths):
        for right in copy_paths[index + 1 :]:
            if _prefix(left, right) or _prefix(right, left):
                raise ReleasePathError("snapshot copies contain a file/ancestor conflict")

    operations: list[_CopyOperation] = []
    for path in copy_paths:
        operations.append(_CopyOperation(path, _source_stat(source_root, path)))
        kind, conflicting_path = _inspect_candidate(candidate_root, path)
        if kind in {"directory", "ancestor_file"}:
            assert conflicting_path is not None
            removals.add(conflicting_path)
    for path in sorted(removals):
        _inspect_candidate(candidate_root, path)
    for path in sorted(removals):
        _preflight_removal(candidate_root, path)
    return _MutationPlan(
        removals=tuple(sorted(removals, key=lambda item: (-len(_parts(item)), item))),
        copies=tuple(operations),
    )


def _preflight_directory_contents(anchor: _DirectoryAnchor) -> None:
    for name, metadata in anchor.entries():
        if _is_link_or_reparse(metadata):
            raise ReleasePathError("removal tree contains a filesystem link")
        if stat.S_ISDIR(metadata.st_mode):
            child = _open_directory_anchor(
                anchor.path / name,
                metadata,
                parent=anchor,
                name=name,
            )
            try:
                _preflight_directory_contents(child)
                child.validate_path()
            finally:
                child.close()
        elif not stat.S_ISREG(metadata.st_mode):
            raise ReleasePathError("removal tree contains an unsupported entry")


def _preflight_removal(root: _DirectoryAnchor, path: str) -> None:
    parts = _parts(path)
    try:
        anchors = _open_chain(root, parts[:-1])
    except ReleasePathError:
        kind, _ = _inspect_candidate(root, path)
        if kind in {"missing", "ancestor_file"}:
            return
        raise
    parent = anchors[-1] if anchors else root
    try:
        metadata = _entry_or_none(parent, parts[-1])
        if metadata is None:
            return
        if _is_link_or_reparse(metadata):
            raise ReleasePathError("removal target is a filesystem link")
        if stat.S_ISDIR(metadata.st_mode):
            child = _open_directory_anchor(
                parent.path / parts[-1],
                metadata,
                parent=parent,
                name=parts[-1],
            )
            try:
                _preflight_directory_contents(child)
                child.validate_path()
            finally:
                child.close()
        elif not stat.S_ISREG(metadata.st_mode):
            raise ReleasePathError("removal target has an unsupported type")
    finally:
        _close_anchors(anchors)


def _remove_directory_contents(anchor: _DirectoryAnchor, *, keep_git: bool = False) -> None:
    for name, metadata in anchor.entries():
        if keep_git and name.lower() == ".git":
            continue
        if _is_link_or_reparse(metadata):
            raise ReleasePathError("recursive removal encountered a filesystem link")
        if stat.S_ISDIR(metadata.st_mode):
            child = _open_directory_anchor(
                anchor.path / name,
                metadata,
                parent=anchor,
                name=name,
            )
            try:
                _remove_directory_contents(child)
                child.validate_path()
            finally:
                child.close()
            anchor.rmdir_entry(name)
        elif stat.S_ISREG(metadata.st_mode):
            anchor.unlink_entry(name)
        else:
            raise ReleasePathError("recursive removal encountered an unsupported type")


def _remove_relative(root: _DirectoryAnchor, path: str) -> None:
    parts = _parts(path)
    try:
        anchors = _open_chain(root, parts[:-1])
    except ReleasePathError:
        kind, _ = _inspect_candidate(root, path)
        if kind in {"missing", "ancestor_file"}:
            return
        raise
    parent = anchors[-1] if anchors else root
    try:
        metadata = _entry_or_none(parent, parts[-1])
        if metadata is None:
            return
        if _is_link_or_reparse(metadata):
            raise ReleasePathError("removal target is a filesystem link")
        if stat.S_ISDIR(metadata.st_mode):
            child = _open_directory_anchor(
                parent.path / parts[-1],
                metadata,
                parent=parent,
                name=parts[-1],
            )
            try:
                _remove_directory_contents(child)
                child.validate_path()
            finally:
                child.close()
            parent.rmdir_entry(parts[-1])
        elif stat.S_ISREG(metadata.st_mode):
            parent.unlink_entry(parts[-1])
        else:
            raise ReleasePathError("removal target has an unsupported type")
    finally:
        _close_anchors(anchors)


def _open_source_file(
    root: _DirectoryAnchor,
    operation: _CopyOperation,
) -> tuple[int, list[_DirectoryAnchor]]:
    parts = _parts(operation.path)
    anchors = _open_chain(root, parts[:-1])
    parent = anchors[-1] if anchors else root
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = parent.open_file(parts[-1], flags)
        opened = os.fstat(descriptor)
        if (
            _is_link_or_reparse(opened)
            or not stat.S_ISREG(opened.st_mode)
            or not _same_identity_and_type(operation.source_stat, opened)
            or operation.source_stat.st_size != opened.st_size
            or operation.source_stat.st_mtime_ns != opened.st_mtime_ns
        ):
            os.close(descriptor)
            raise ReleasePathError("source file identity changed before copy")
        return descriptor, anchors
    except BaseException:
        _close_anchors(anchors)
        raise


def _set_temp_metadata(
    parent: _DirectoryAnchor,
    name: str,
    source_stat: os.stat_result,
    descriptor: int,
) -> None:
    if isinstance(parent, _PosixDirectoryAnchor):
        os.fchmod(descriptor, stat.S_IMODE(source_stat.st_mode))
        os.utime(descriptor, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
    else:
        assert os.name == "nt"
        handle = msvcrt.get_osfhandle(descriptor)
        attributes = getattr(source_stat, "st_file_attributes", 0) or 0x80
        information = _FileBasicInformation(
            0,
            source_stat.st_atime_ns // 100 + _WINDOWS_EPOCH_TICKS,
            source_stat.st_mtime_ns // 100 + _WINDOWS_EPOCH_TICKS,
            0,
            attributes,
        )
        if not _set_file_information(
            handle,
            _FILE_BASIC_INFO_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            raise ReleasePathError("could not apply metadata through open file handle")


def _copy_regular_file_anchored(
    source_root: _DirectoryAnchor,
    candidate_root: _DirectoryAnchor,
    operation: _CopyOperation,
) -> None:
    source_descriptor, source_anchors = _open_source_file(source_root, operation)
    parts = _parts(operation.path)
    candidate_anchors = _open_chain(candidate_root, parts[:-1], create=True)
    parent = candidate_anchors[-1] if candidate_anchors else candidate_root
    temporary = f".nova-release-{secrets.token_hex(12)}.tmp"
    destination_descriptor = -1
    temporary_created = False
    try:
        existing = _entry_or_none(parent, parts[-1])
        if existing is not None and (
            _is_link_or_reparse(existing) or not stat.S_ISREG(existing.st_mode)
        ):
            raise ReleasePathError("copy destination changed to an unsafe type")
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        destination_descriptor = parent.open_file(temporary, flags, 0o600)
        temporary_created = True
        while block := os.read(source_descriptor, _COPY_BLOCK_SIZE):
            view = memoryview(block)
            while view:
                written = os.write(destination_descriptor, view)
                view = view[written:]
        os.fsync(destination_descriptor)
        _set_temp_metadata(
            parent,
            temporary,
            operation.source_stat,
            destination_descriptor,
        )
        os.close(destination_descriptor)
        destination_descriptor = -1
        current_source = os.fstat(source_descriptor)
        if (
            not _same_identity_and_type(operation.source_stat, current_source)
            or operation.source_stat.st_size != current_source.st_size
            or operation.source_stat.st_mtime_ns != current_source.st_mtime_ns
        ):
            raise ReleasePathError("source file changed during copy")
        source_parent = source_anchors[-1] if source_anchors else source_root
        source_name = _parts(operation.path)[-1]
        current_source_path = source_parent.stat_entry(source_name)
        if (
            _is_link_or_reparse(current_source_path)
            or not _same_identity_and_type(operation.source_stat, current_source_path)
            or operation.source_stat.st_size != current_source_path.st_size
            or operation.source_stat.st_mtime_ns != current_source_path.st_mtime_ns
        ):
            raise ReleasePathError("source pathname changed during copy")
        current_destination = _entry_or_none(parent, parts[-1])
        if existing is None:
            if current_destination is not None:
                raise ReleasePathError("candidate entry appeared before atomic replace")
        elif (
            current_destination is None
            or _is_link_or_reparse(current_destination)
            or not stat.S_ISREG(current_destination.st_mode)
            or not _same_identity_and_type(existing, current_destination)
        ):
            raise ReleasePathError("candidate entry identity changed before atomic replace")
        parent.validate_path()
        parent.replace_entry(temporary, parts[-1])
        temporary_created = False
    finally:
        if destination_descriptor >= 0:
            os.close(destination_descriptor)
        if temporary_created:
            metadata = _entry_or_none(parent, temporary)
            if metadata is not None and stat.S_ISREG(metadata.st_mode):
                parent.unlink_entry(temporary)
        os.close(source_descriptor)
        _close_anchors(candidate_anchors)
        _close_anchors(source_anchors)


def _apply_mutation_plan(
    source_root: _DirectoryAnchor,
    candidate_root: _DirectoryAnchor,
    plan: _MutationPlan,
) -> None:
    source_root.validate_path()
    candidate_root.validate_path()
    for path in plan.removals:
        _remove_relative(candidate_root, path)
    for operation in plan.copies:
        _copy_regular_file_anchored(source_root, candidate_root, operation)
    source_root.validate_path()
    candidate_root.validate_path()


def _open_candidate_from_temp(
    temp_anchor: _DirectoryAnchor,
    relative_parts: tuple[str, ...],
) -> tuple[_DirectoryAnchor, list[_DirectoryAnchor]]:
    anchors = _open_chain(temp_anchor, relative_parts)
    if not anchors:
        raise ReleasePathError("candidate must be a strict temporary descendant")
    return anchors[-1], anchors


def apply_snapshot(
    source: str | Path,
    candidate: str | Path,
    report: SnapshotReport,
    approved_temp_root: str | Path,
) -> None:
    """Apply a fully preflighted snapshot through anchored filesystem operations."""

    if report.ambiguous:
        raise AmbiguousSnapshotError("snapshot report contains ambiguous decisions")
    source_path = _absolute_input(source, "source root")
    if source_path.resolve() != source_path:
        raise ReleasePathError("source root is below a linked filesystem ancestor")
    source_anchor = _open_directory_anchor(source_path)
    temp_anchor: _DirectoryAnchor | None = None
    candidate_anchors: list[_DirectoryAnchor] = []
    try:
        temp_root, temp_anchor = _verified_temp_root(approved_temp_root, source_path)
        _candidate_path, relative_parts = _safe_destination(candidate, temp_root)
        candidate_anchor, candidate_anchors = _open_candidate_from_temp(temp_anchor, relative_parts)
        plan = _build_mutation_plan(source_anchor, candidate_anchor, report)
        _apply_mutation_plan(source_anchor, candidate_anchor, plan)
        temp_anchor.validate_path()
    finally:
        _close_anchors(candidate_anchors)
        if temp_anchor is not None:
            temp_anchor.close()
        source_anchor.close()


def remove_candidate_paths(
    candidate: str | Path,
    paths: Iterable[str],
    approved_temp_root: str | Path,
    protected_repository_root: str | Path,
) -> None:
    """Remove approved candidate-relative paths through anchored operations."""

    candidate_path = _absolute_input(candidate, "candidate root")
    temp_root, temp_anchor = _verified_temp_root(
        approved_temp_root,
        protected_repository_root,
    )
    candidate_anchors: list[_DirectoryAnchor] = []
    try:
        _candidate_path, relative_parts = _safe_destination(candidate_path, temp_root)
        candidate_anchor, candidate_anchors = _open_candidate_from_temp(
            temp_anchor,
            relative_parts,
        )
        normalized = sorted(
            {_normalized_relative_path(path) for path in paths},
            key=lambda item: (len(_parts(item)), item),
        )
        roots: list[str] = []
        for path in normalized:
            if not any(_prefix(existing, path) for existing in roots):
                roots.append(path)
        for path in roots:
            _preflight_removal(candidate_anchor, path)
        for path in roots:
            _remove_relative(candidate_anchor, path)
        candidate_anchor.validate_path()
        temp_anchor.validate_path()
    finally:
        _close_anchors(candidate_anchors)
        temp_anchor.close()


def commit_candidate(candidate: str | Path, message: str) -> str:
    candidate_path = _absolute_input(candidate, "candidate root")
    if candidate_path.resolve() != candidate_path:
        raise ReleasePathError("candidate root is below a linked filesystem ancestor")
    anchor = _open_directory_anchor(candidate_path)
    try:
        git_output(candidate_path, "add", "-A")
        anchor.validate_path()
        git_output(candidate_path, "commit", "-m", message)
        anchor.validate_path()
        return git_output(candidate_path, "rev-parse", "HEAD")
    finally:
        anchor.close()


def _remove_candidate_tree_anchored(candidate_anchor: _DirectoryAnchor) -> None:
    candidate_anchor.validate_path()
    _remove_directory_contents(candidate_anchor)
    candidate_anchor.validate_path()


def _registered_worktree_count(repository: GitRepository, destination: Path) -> int:
    expected = os.path.normcase(str(destination.resolve()))
    matches = 0
    for line in git_output(repository.root, "worktree", "list", "--porcelain").splitlines():
        if not line.startswith("worktree "):
            continue
        registered = os.path.normcase(str(Path(line.removeprefix("worktree ")).resolve()))
        if registered == expected:
            matches += 1
    return matches


def _worktree_is_registered(repository: GitRepository, destination: Path) -> bool:
    return _registered_worktree_count(repository, destination) == 1


def _read_anchored_regular_file(anchor: _DirectoryAnchor, name: str) -> bytes:
    expected = anchor.stat_entry(name)
    if _is_link_or_reparse(expected) or not stat.S_ISREG(expected.st_mode):
        raise ReleasePathError("worktree administrative pointer is not a regular file")
    if expected.st_size > 1024 * 1024:
        raise ReleasePathError("worktree administrative pointer is unexpectedly large")
    descriptor = anchor.open_file(
        name,
        os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if not _same_identity_and_type(expected, opened):
            raise ReleasePathError("worktree administrative pointer identity changed")
        chunks: list[bytes] = []
        total = 0
        while block := os.read(descriptor, 64 * 1024):
            total += len(block)
            if total > 1024 * 1024:
                raise ReleasePathError("worktree administrative pointer is unexpectedly large")
            chunks.append(block)
        current = anchor.stat_entry(name)
        if not _same_identity_and_type(expected, current):
            raise ReleasePathError("worktree administrative pointer identity changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _write_anchored_regular_file(anchor: _DirectoryAnchor, name: str, data: bytes) -> None:
    descriptor = anchor.open_file(
        name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_placeholder(
    parent: _DirectoryAnchor,
    name: str,
    expected: os.stat_result,
) -> None:
    current = _entry_or_none(parent, name)
    if current is None:
        return
    if (
        _is_link_or_reparse(current)
        or not stat.S_ISDIR(current.st_mode)
        or not _same_identity_and_type(expected, current)
    ):
        raise ReleasePathError("cleanup placeholder identity changed")
    anchor = _open_directory_anchor(
        parent.path / name,
        current,
        parent=parent,
        name=name,
    )
    try:
        _remove_directory_contents(anchor)
        anchor.validate_path()
    finally:
        anchor.close()
    parent.rmdir_entry(name)


def _rollback_quarantined_candidate(
    parent: _DirectoryAnchor,
    candidate_name: str,
    placeholder_stat: os.stat_result | None,
    quarantine_name: str,
    candidate_identity: os.stat_result,
) -> None:
    quarantined = _entry_or_none(parent, quarantine_name)
    current_candidate = _entry_or_none(parent, candidate_name)
    if quarantined is None:
        if (
            current_candidate is not None
            and not _is_link_or_reparse(current_candidate)
            and stat.S_ISDIR(current_candidate.st_mode)
            and _same_identity_and_type(candidate_identity, current_candidate)
        ):
            return
        raise ReleasePathError("cleanup quarantine is unavailable for rollback")
    if (
        _is_link_or_reparse(quarantined)
        or not stat.S_ISDIR(quarantined.st_mode)
        or not _same_identity_and_type(candidate_identity, quarantined)
    ):
        raise ReleasePathError("cleanup quarantine identity changed before rollback")
    if current_candidate is not None:
        expected_placeholder = placeholder_stat or current_candidate
        if (
            _is_link_or_reparse(current_candidate)
            or not stat.S_ISDIR(current_candidate.st_mode)
            or not _same_identity_and_type(expected_placeholder, current_candidate)
        ):
            raise ReleasePathError("cleanup placeholder identity changed before rollback")
        _remove_placeholder(parent, candidate_name, expected_placeholder)
    parent.replace_entry(quarantine_name, candidate_name)
    restored = parent.stat_entry(candidate_name)
    if not _same_identity_and_type(candidate_identity, restored):
        raise ReleasePathError("candidate identity changed during cleanup rollback")


def _bounded_recovery_path(path: Path) -> str:
    rendered = str(path)
    return rendered if len(rendered) <= 900 else "..." + rendered[-897:]


def _cleanup_recovery_error(destination: Path, quarantine: Path) -> GitError:
    return GitError(
        "Cleanup rollback failed; manual recovery is required. "
        f"Candidate path: {_bounded_recovery_path(destination)}; "
        f"intact quarantine path: {_bounded_recovery_path(quarantine)}"
    )


def _git_failure(repository: GitRepository, args: tuple[str, ...], stderr: str) -> GitError:
    return GitError(
        "Git failed during reversible worktree cleanup: "
        + _redacted_stderr(repository.root, args, stderr)
    )


def cleanup_worktree(
    repository: GitRepository,
    destination: str | Path,
    approved_temp_root: str | Path,
) -> None:
    """Reversibly unregister, then delete one exactly registered candidate."""

    temp_root, temp_anchor = _verified_temp_root(approved_temp_root, repository.root)
    candidate_anchors: list[_DirectoryAnchor] = []
    try:
        destination_path, relative_parts = _safe_destination(destination, temp_root)
        if _registered_worktree_count(repository, destination_path) != 1:
            raise GitError("cleanup destination is not exactly one registered worktree")
        candidate_anchor, candidate_anchors = _open_candidate_from_temp(
            temp_anchor,
            relative_parts,
        )
        _preflight_directory_contents(candidate_anchor)
        candidate_anchor.validate_path()
        candidate_identity = candidate_anchor.opened
        git_pointer = _read_anchored_regular_file(candidate_anchor, ".git")
        candidate_parent = (
            candidate_anchors[-2] if len(candidate_anchors) > 1 else temp_anchor
        )
        candidate_name = relative_parts[-1]
        quarantine_name = f".nova-release-cleanup-{secrets.token_hex(12)}"
        if _entry_or_none(candidate_parent, quarantine_name) is not None:
            raise ReleasePathError("cleanup quarantine already exists")
        candidate_anchors.pop()
        candidate_anchor.close()
        placeholder_stat: os.stat_result | None = None
        placeholder_anchor: _DirectoryAnchor | None = None
        try:
            candidate_parent.replace_entry(candidate_name, quarantine_name)
            quarantined = candidate_parent.stat_entry(quarantine_name)
            if not _same_identity_and_type(candidate_identity, quarantined):
                raise ReleasePathError("candidate identity changed during quarantine")
            candidate_parent.mkdir_entry(candidate_name)
            placeholder_stat = candidate_parent.stat_entry(candidate_name)
            placeholder_anchor = _open_directory_anchor(
                candidate_parent.path / candidate_name,
                placeholder_stat,
                parent=candidate_parent,
                name=candidate_name,
            )
            _write_anchored_regular_file(placeholder_anchor, ".git", git_pointer)
            git_args = ("worktree", "remove", "--force", str(destination_path))
            try:
                completed = _run_git(repository.root, *git_args)
                registered_after = _worktree_is_registered(repository, destination_path)
            except GitError as error:
                registered_after = True
                git_error: GitError = error
            else:
                git_error = _git_failure(repository, git_args, completed.stderr)

            placeholder_entries = placeholder_anchor.entries()
            if registered_after or placeholder_entries:
                raise git_error
        except Exception:
            if placeholder_anchor is not None:
                try:
                    placeholder_anchor.close()
                except Exception:
                    pass
                placeholder_anchor = None
            try:
                _rollback_quarantined_candidate(
                    candidate_parent,
                    candidate_name,
                    placeholder_stat,
                    quarantine_name,
                    candidate_identity,
                )
            except Exception:
                raise _cleanup_recovery_error(
                    destination_path,
                    candidate_parent.path / quarantine_name,
                ) from None
            raise
        finally:
            if placeholder_anchor is not None:
                placeholder_anchor.close()

        remaining = _entry_or_none(candidate_parent, candidate_name)
        assert placeholder_stat is not None
        if remaining is not None:
            if (
                _is_link_or_reparse(remaining)
                or not stat.S_ISDIR(remaining.st_mode)
                or not _same_identity_and_type(placeholder_stat, remaining)
            ):
                raise ReleasePathError("cleanup placeholder identity changed")
            candidate_parent.rmdir_entry(candidate_name)

        quarantine_stat = candidate_parent.stat_entry(quarantine_name)
        if not _same_identity_and_type(candidate_identity, quarantine_stat):
            raise ReleasePathError("quarantined candidate identity changed")
        quarantine_anchor = _open_directory_anchor(
            candidate_parent.path / quarantine_name,
            quarantine_stat,
            parent=candidate_parent,
            name=quarantine_name,
        )
        try:
            _remove_candidate_tree_anchored(quarantine_anchor)
            quarantine_anchor.validate_path()
        finally:
            quarantine_anchor.close()
        current_quarantine = candidate_parent.stat_entry(quarantine_name)
        if not _same_identity_and_type(candidate_identity, current_quarantine):
            raise ReleasePathError("quarantined candidate identity changed before removal")
        candidate_parent.rmdir_entry(quarantine_name)
        _close_anchors(candidate_anchors)
        candidate_anchors = []
        temp_anchor.validate_path()
    finally:
        _close_anchors(candidate_anchors)
        temp_anchor.close()
