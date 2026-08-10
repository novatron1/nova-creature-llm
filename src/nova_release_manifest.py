"""Deterministic release manifests and local release-run state."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping

if os.name == "nt":
    import ctypes
    from ctypes import wintypes


MANIFEST_SCHEMA_VERSION = "1.0"
MANIFEST_NAME = "NOVA_RELEASE_MANIFEST.json"
_HASH_BLOCK_SIZE = 1024 * 1024

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


@dataclass(frozen=True)
class FileDigest:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class GateSummary:
    name: str
    passed: bool


@dataclass
class ReleaseManifest:
    schema_version: str
    release_id: str
    source_branch: str
    source_commit: str
    candidate_branch: str
    files: list[FileDigest]
    excluded_counts: dict[str, int]
    deletions: list[str]
    gates: list[GateSummary]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RunReport:
    schema_version: str
    run_id: str
    status: str
    started_at: str
    source_commit: str
    candidate_branch: str | None = None
    candidate_commit: str | None = None
    master_before: str | None = None
    master_after: str | None = None
    rollback_ref: str | None = None
    failure_gate: str | None = None
    gates: list[dict[str, object]] = field(default_factory=list)


def canonical_json(value: object) -> str:
    """Serialize a JSON-compatible value in the manifest's canonical form."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Return a file's SHA-256 digest, reading it in bounded blocks."""

    _, digest = _hash_regular_file(Path(path))
    return digest


def _stat_identity(stat_result: os.stat_result) -> tuple[int, int]:
    return stat_result.st_dev, stat_result.st_ino


def _stable_file_metadata(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        _stat_identity(left) == _stat_identity(right)
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )


def _same_identity_and_type(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        _stat_identity(left) == _stat_identity(right)
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
    )


def _hash_regular_file(
    path: Path,
    expected_stat: os.stat_result | None = None,
    *,
    dir_fd: int | None = None,
    display_path: Path | None = None,
) -> tuple[int, str]:
    shown_path = display_path or path
    before_open = os.stat(path, dir_fd=dir_fd, follow_symlinks=False)
    if _is_link_or_reparse(before_open) or not stat.S_ISREG(before_open.st_mode):
        raise OSError(f"refusing to hash non-regular or linked file: {shown_path}")
    if expected_stat is not None and not _stable_file_metadata(
        expected_stat, before_open
    ):
        raise OSError(f"file identity changed before secure open: {shown_path}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if dir_fd is None:
        descriptor = os.open(path, flags)
    else:
        descriptor = os.open(path, flags, dir_fd=dir_fd)
    digest = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if (
            _is_link_or_reparse(opened)
            or not stat.S_ISREG(opened.st_mode)
            or not _stable_file_metadata(before_open, opened)
        ):
            raise OSError(f"file identity changed during secure open: {shown_path}")
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            size_bytes = 0
            while block := handle.read(_HASH_BLOCK_SIZE):
                size_bytes += len(block)
                digest.update(block)
            after_read = os.fstat(handle.fileno())
        if not _stable_file_metadata(opened, after_read) or size_bytes != opened.st_size:
            raise OSError(f"file changed while hashing: {shown_path}")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return size_bytes, digest.hexdigest()


def release_state_root(git_common_dir: str | os.PathLike[str]) -> Path:
    """Return the repository-local administrative root for release state."""

    common_dir = Path(git_common_dir)
    common_resolved = _validated_directory(common_dir, "Git common directory")
    state_root = common_dir / "nova-release-lock"
    try:
        state_stat = state_root.stat(follow_symlinks=False)
    except FileNotFoundError:
        return state_root
    if _is_link_or_reparse(state_stat):
        raise OSError(f"release state root is a filesystem link or reparse point: {state_root}")
    if not stat.S_ISDIR(state_stat.st_mode):
        raise OSError(f"release state root is not a directory: {state_root}")
    state_resolved = state_root.resolve(strict=True)
    if not state_resolved.is_relative_to(common_resolved):
        raise OSError(f"release state root escapes Git common directory: {state_root}")
    return state_root


def write_json_atomic(path: str | os.PathLike[str], value: object) -> None:
    """Durably write canonical JSON before atomically replacing ``path``."""

    destination = Path(path)
    serialized = canonical_json(value)
    anchors = _open_write_parent_anchors(destination)
    parent_anchor = anchors[-1]
    temporary_name = f"{destination.name}.tmp"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    created_stat: os.stat_result | None = None
    try:
        _validate_destination_entry(destination)
        _validate_anchored_destination(parent_anchor, destination.name, destination)
        descriptor = parent_anchor.open_file(temporary_name, flags, 0o600)
        created_stat = os.fstat(descriptor)
        if _is_link_or_reparse(created_stat) or not stat.S_ISREG(created_stat.st_mode):
            raise OSError(
                f"atomic temporary path is not a regular file: {destination.parent / temporary_name}"
            )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        _validate_anchored_temporary(
            parent_anchor,
            temporary_name,
            created_stat,
            destination,
        )
        _validate_destination_entry(destination)
        _validate_anchored_destination(parent_anchor, destination.name, destination)
        parent_anchor.validate_path()
        parent_anchor.replace_entry(temporary_name, destination.name)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if created_stat is not None:
            _remove_anchored_temporary(
                parent_anchor,
                temporary_name,
                created_stat,
            )
        for anchor in reversed(anchors):
            anchor.close()


def _is_link_or_reparse(stat_result: os.stat_result) -> bool:
    if stat.S_ISLNK(stat_result.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(reparse_flag and file_attributes & reparse_flag)


def _validated_directory(path: Path, label: str) -> Path:
    stat_result = path.stat(follow_symlinks=False)
    if _is_link_or_reparse(stat_result):
        raise OSError(f"{label} is a filesystem link or reparse point: {path}")
    if not stat.S_ISDIR(stat_result.st_mode):
        raise OSError(f"{label} is not a directory: {path}")
    return path.resolve(strict=True)


def _release_state_ancestor(path: Path) -> Path | None:
    matches = [parent for parent in path.parents if parent.name == "nova-release-lock"]
    if not matches:
        return None
    if len(matches) != 1:
        raise OSError(f"ambiguous release state path: {path}")
    return matches[0]


def _prepare_write_parent(destination: Path) -> None:
    state_root = _release_state_ancestor(destination)
    if state_root is None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        return

    common_dir = state_root.parent
    trusted_common = _validated_directory(common_dir, "Git common directory")
    if release_state_root(common_dir) != state_root:
        raise OSError(f"invalid release state path: {destination}")
    relative_parent = destination.parent.relative_to(common_dir)
    current = common_dir
    for part in relative_parent.parts:
        if part in {".", ".."}:
            raise OSError(f"release state path contains unsafe traversal: {destination}")
        current = current / part
        try:
            current.mkdir()
        except FileExistsError:
            pass
        resolved = _validated_directory(current, "release state path component")
        if not resolved.is_relative_to(trusted_common):
            raise OSError(f"release state path escapes Git common directory: {destination}")


def _open_write_parent_anchors(destination: Path) -> list[_DirectoryAnchor]:
    _prepare_write_parent(destination)
    state_root = _release_state_ancestor(destination)
    if state_root is None:
        anchor_paths = [destination.parent]
    else:
        common_dir = state_root.parent
        relative_parent = destination.parent.relative_to(common_dir)
        anchor_paths = [common_dir]
        current = common_dir
        for part in relative_parent.parts:
            current = current / part
            anchor_paths.append(current)

    anchors: list[_DirectoryAnchor] = []
    try:
        for path in anchor_paths:
            if not anchors:
                anchor = _open_directory_anchor(path)
            else:
                parent = anchors[-1]
                expected = parent.stat_entry(path.name)
                anchor = _open_directory_anchor(
                    path,
                    expected,
                    parent=parent,
                    name=path.name,
                )
            anchors.append(anchor)
    except BaseException:
        for anchor in reversed(anchors):
            anchor.close()
        raise
    return anchors


def _validate_destination_entry(destination: Path) -> None:
    try:
        destination_stat = destination.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if _is_link_or_reparse(destination_stat) or not stat.S_ISREG(
        destination_stat.st_mode
    ):
        raise OSError(f"atomic destination is not a regular unlinked file: {destination}")


def _validate_anchored_destination(
    anchor: _DirectoryAnchor,
    name: str,
    destination: Path,
) -> None:
    try:
        destination_stat = anchor.stat_entry(name)
    except FileNotFoundError:
        return
    if _is_link_or_reparse(destination_stat) or not stat.S_ISREG(
        destination_stat.st_mode
    ):
        raise OSError(f"atomic destination is not a regular unlinked file: {destination}")


def _validate_anchored_temporary(
    anchor: _DirectoryAnchor,
    name: str,
    created_stat: os.stat_result,
    destination: Path,
) -> None:
    current = anchor.stat_entry(name)
    if (
        _is_link_or_reparse(current)
        or not stat.S_ISREG(current.st_mode)
        or not _same_identity_and_type(created_stat, current)
    ):
        raise OSError(
            f"atomic temporary identity changed: {destination.parent / name}"
        )


def _remove_anchored_temporary(
    anchor: _DirectoryAnchor,
    name: str,
    created_stat: os.stat_result,
) -> None:
    try:
        current = anchor.stat_entry(name)
    except FileNotFoundError:
        return
    if (
        not _is_link_or_reparse(current)
        and stat.S_ISREG(current.st_mode)
        and _same_identity_and_type(created_stat, current)
    ):
        anchor.unlink_entry(name)


class _DirectoryAnchor:
    path: Path

    def entries(self) -> list[tuple[str, os.stat_result]]:
        raise NotImplementedError

    def hash_file(self, name: str, expected_stat: os.stat_result) -> tuple[int, str]:
        raise NotImplementedError

    def stat_entry(self, name: str) -> os.stat_result:
        raise NotImplementedError

    def open_file(self, name: str, flags: int, mode: int = 0o777) -> int:
        raise NotImplementedError

    def replace_entry(self, source: str, destination: str) -> None:
        raise NotImplementedError

    def unlink_entry(self, name: str) -> None:
        raise NotImplementedError

    def validate_path(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class _PosixDirectoryAnchor(_DirectoryAnchor):
    def __init__(self, path: Path, descriptor: int, opened_stat: os.stat_result) -> None:
        self.path = path
        self.descriptor = descriptor
        self.opened_stat = opened_stat

    def entries(self) -> list[tuple[str, os.stat_result]]:
        self.validate_path()
        with os.scandir(self.descriptor) as iterator:
            return sorted(
                (
                    (entry.name, entry.stat(follow_symlinks=False))
                    for entry in iterator
                ),
                key=lambda item: item[0],
            )

    def hash_file(self, name: str, expected_stat: os.stat_result) -> tuple[int, str]:
        return _hash_regular_file(
            Path(name),
            expected_stat,
            dir_fd=self.descriptor,
            display_path=self.path / name,
        )

    def stat_entry(self, name: str) -> os.stat_result:
        return os.stat(name, dir_fd=self.descriptor, follow_symlinks=False)

    def open_file(self, name: str, flags: int, mode: int = 0o777) -> int:
        self.validate_path()
        return os.open(name, flags, mode, dir_fd=self.descriptor)

    def replace_entry(self, source: str, destination: str) -> None:
        self.validate_path()
        os.replace(
            source,
            destination,
            src_dir_fd=self.descriptor,
            dst_dir_fd=self.descriptor,
        )

    def unlink_entry(self, name: str) -> None:
        os.unlink(name, dir_fd=self.descriptor)

    def validate_path(self) -> None:
        current = self.path.stat(follow_symlinks=False)
        opened = os.fstat(self.descriptor)
        if (
            _is_link_or_reparse(current)
            or not stat.S_ISDIR(current.st_mode)
            or not _same_identity_and_type(self.opened_stat, current)
            or not _same_identity_and_type(self.opened_stat, opened)
        ):
            raise OSError(f"directory identity changed while anchored: {self.path}")

    def close(self) -> None:
        os.close(self.descriptor)


if os.name == "nt":

    def _windows_handle_information(handle: int) -> _ByHandleFileInformation:
        information = _ByHandleFileInformation()
        if not _get_file_information(handle, ctypes.byref(information)):
            raise ctypes.WinError(ctypes.get_last_error())
        return information


    def _windows_file_index(information: _ByHandleFileInformation) -> int:
        return (information.nFileIndexHigh << 32) | information.nFileIndexLow


    class _WindowsDirectoryAnchor(_DirectoryAnchor):
        def __init__(
            self,
            path: Path,
            handle: int,
            opened_stat: os.stat_result,
            file_index: int,
        ) -> None:
            self.path = path
            self.handle = handle
            self.opened_stat = opened_stat
            self.file_index = file_index

        def entries(self) -> list[tuple[str, os.stat_result]]:
            self.validate_path()
            with os.scandir(self.path) as iterator:
                return sorted(
                    (
                        (
                            entry.name,
                            (self.path / entry.name).stat(follow_symlinks=False),
                        )
                        for entry in iterator
                    ),
                    key=lambda item: item[0],
                )

        def hash_file(
            self,
            name: str,
            expected_stat: os.stat_result,
        ) -> tuple[int, str]:
            self.validate_path()
            return _hash_regular_file(self.path / name, expected_stat)

        def stat_entry(self, name: str) -> os.stat_result:
            self.validate_path()
            return (self.path / name).stat(follow_symlinks=False)

        def open_file(self, name: str, flags: int, mode: int = 0o777) -> int:
            self.validate_path()
            return os.open(self.path / name, flags, mode)

        def replace_entry(self, source: str, destination: str) -> None:
            self.validate_path()
            os.replace(self.path / source, self.path / destination)

        def unlink_entry(self, name: str) -> None:
            os.unlink(self.path / name)

        def validate_path(self) -> None:
            current = self.path.stat(follow_symlinks=False)
            information = _windows_handle_information(self.handle)
            if (
                _is_link_or_reparse(current)
                or not stat.S_ISDIR(current.st_mode)
                or not _same_identity_and_type(self.opened_stat, current)
                or information.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT
                or not information.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY
                or _windows_file_index(information) != current.st_ino
            ):
                raise OSError(f"directory identity changed while anchored: {self.path}")

        def close(self) -> None:
            if not _close_handle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())


def _open_directory_anchor(
    path: Path,
    expected_stat: os.stat_result | None = None,
    *,
    parent: _DirectoryAnchor | None = None,
    name: str | None = None,
) -> _DirectoryAnchor:
    if parent is not None:
        parent.validate_path()

    if os.name == "nt":
        before_open = path.stat(follow_symlinks=False)
        if expected_stat is not None and not _stable_file_metadata(
            expected_stat, before_open
        ):
            raise OSError(f"directory identity changed before secure open: {path}")
        if _is_link_or_reparse(before_open) or not stat.S_ISDIR(before_open.st_mode):
            raise OSError(f"refusing to open linked or non-directory path: {path}")
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
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            information = _windows_handle_information(handle)
            after_open = path.stat(follow_symlinks=False)
            if (
                not _stable_file_metadata(before_open, after_open)
                or information.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT
                or not information.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY
                or _windows_file_index(information) != after_open.st_ino
            ):
                raise OSError(f"directory identity changed during secure open: {path}")
            return _WindowsDirectoryAnchor(
                path,
                handle,
                after_open,
                _windows_file_index(information),
            )
        except BaseException:
            _close_handle(handle)
            raise

    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    if parent is None:
        before_open = path.stat(follow_symlinks=False)
        descriptor = os.open(path, flags)
    else:
        if not isinstance(parent, _PosixDirectoryAnchor) or name is None:
            raise OSError(f"invalid anchored directory parent for: {path}")
        before_open = os.stat(name, dir_fd=parent.descriptor, follow_symlinks=False)
        descriptor = os.open(name, flags, dir_fd=parent.descriptor)
    try:
        if expected_stat is not None and not _stable_file_metadata(
            expected_stat, before_open
        ):
            raise OSError(f"directory identity changed before secure open: {path}")
        opened = os.fstat(descriptor)
        if (
            _is_link_or_reparse(before_open)
            or not stat.S_ISDIR(before_open.st_mode)
            or not _stable_file_metadata(before_open, opened)
        ):
            raise OSError(f"directory identity changed during secure open: {path}")
        return _PosixDirectoryAnchor(path, descriptor, opened)
    except BaseException:
        os.close(descriptor)
        raise


def _validated_manifest_root(root: Path) -> Path:
    stat_result = root.stat(follow_symlinks=False)
    if _is_link_or_reparse(stat_result):
        raise OSError(f"manifest root is a filesystem link or reparse point: {root}")
    if not stat.S_ISDIR(stat_result.st_mode):
        raise OSError(f"manifest root is not a directory: {root}")
    return root


def _anchored_manifest_files(root: Path) -> list[FileDigest]:
    files: list[FileDigest] = []
    root_anchor = _open_directory_anchor(root)
    try:
        _scan_anchored_directory(root_anchor, "", files)
    finally:
        root_anchor.close()
    return sorted(files, key=lambda item: item.path)


def _scan_anchored_directory(
    anchor: _DirectoryAnchor,
    relative_directory: str,
    files: list[FileDigest],
) -> None:
    for name, entry_stat in anchor.entries():
        if name == ".git":
            continue
        relative = f"{relative_directory}/{name}" if relative_directory else name
        if _is_link_or_reparse(entry_stat):
            continue
        if stat.S_ISDIR(entry_stat.st_mode):
            child_path = anchor.path / name
            child = _open_directory_anchor(
                child_path,
                entry_stat,
                parent=anchor,
                name=name,
            )
            try:
                _scan_anchored_directory(child, relative, files)
            finally:
                child.close()
            continue
        if not stat.S_ISREG(entry_stat.st_mode) or relative == MANIFEST_NAME:
            continue
        size_bytes, digest = anchor.hash_file(name, entry_stat)
        files.append(
            FileDigest(path=relative, size_bytes=size_bytes, sha256=digest)
        )


def build_content_manifest(
    root: str | os.PathLike[str],
    *,
    source_branch: str,
    source_commit: str,
    candidate_branch: str,
    excluded_counts: Mapping[str, int],
    deletions: list[str],
    gates: Mapping[str, bool],
) -> ReleaseManifest:
    """Build a canonical content manifest from the regular files under ``root``."""

    root_path = _validated_manifest_root(Path(root))
    files = _anchored_manifest_files(root_path)
    sorted_excluded_counts = dict(sorted(excluded_counts.items()))
    sorted_deletions = sorted(deletions)
    sorted_gates = [
        GateSummary(name=name, passed=passed) for name, passed in sorted(gates.items())
    ]
    content_fields = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "source_branch": source_branch,
        "source_commit": source_commit,
        "candidate_branch": candidate_branch,
        "files": [asdict(item) for item in files],
        "excluded_counts": sorted_excluded_counts,
        "deletions": sorted_deletions,
        "gates": [asdict(item) for item in sorted_gates],
    }
    content_digest = hashlib.sha256(
        canonical_json(content_fields).encode("utf-8")
    ).hexdigest()

    return ReleaseManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        release_id=f"{source_commit}-{content_digest}",
        source_branch=source_branch,
        source_commit=source_commit,
        candidate_branch=candidate_branch,
        files=files,
        excluded_counts=sorted_excluded_counts,
        deletions=sorted_deletions,
        gates=sorted_gates,
    )
