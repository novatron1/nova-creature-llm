"""Deterministic release manifests and local release-run state."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping


MANIFEST_SCHEMA_VERSION = "1.0"
MANIFEST_NAME = "NOVA_RELEASE_MANIFEST.json"
_HASH_BLOCK_SIZE = 1024 * 1024


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
) -> tuple[int, str]:
    before_open = path.stat(follow_symlinks=False)
    if _is_link_or_reparse(before_open) or not stat.S_ISREG(before_open.st_mode):
        raise OSError(f"refusing to hash non-regular or linked file: {path}")
    if expected_stat is not None and not _stable_file_metadata(
        expected_stat, before_open
    ):
        raise OSError(f"file identity changed before secure open: {path}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if (
            _is_link_or_reparse(opened)
            or not stat.S_ISREG(opened.st_mode)
            or not _stable_file_metadata(before_open, opened)
        ):
            raise OSError(f"file identity changed during secure open: {path}")
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            size_bytes = 0
            while block := handle.read(_HASH_BLOCK_SIZE):
                size_bytes += len(block)
                digest.update(block)
            after_read = os.fstat(handle.fileno())
        if not _stable_file_metadata(opened, after_read) or size_bytes != opened.st_size:
            raise OSError(f"file changed while hashing: {path}")
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
    _prepare_write_parent(destination)
    _validate_destination_entry(destination)
    temporary = destination.with_name(f"{destination.name}.tmp")
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
        descriptor = os.open(temporary, flags, 0o600)
        created_stat = os.fstat(descriptor)
        if _is_link_or_reparse(created_stat) or not stat.S_ISREG(created_stat.st_mode):
            raise OSError(f"atomic temporary path is not a regular file: {temporary}")
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        _validate_owned_temporary(temporary, created_stat)
        _prepare_write_parent(destination)
        _validate_destination_entry(destination)
        os.replace(temporary, destination)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if created_stat is not None:
            _remove_owned_temporary(temporary, created_stat)


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


def _validate_destination_entry(destination: Path) -> None:
    try:
        destination_stat = destination.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if _is_link_or_reparse(destination_stat) or not stat.S_ISREG(
        destination_stat.st_mode
    ):
        raise OSError(f"atomic destination is not a regular unlinked file: {destination}")


def _validate_owned_temporary(temporary: Path, created_stat: os.stat_result) -> None:
    current = temporary.stat(follow_symlinks=False)
    if (
        _is_link_or_reparse(current)
        or not stat.S_ISREG(current.st_mode)
        or not _same_identity_and_type(created_stat, current)
    ):
        raise OSError(f"atomic temporary identity changed: {temporary}")


def _remove_owned_temporary(temporary: Path, created_stat: os.stat_result) -> None:
    try:
        current = temporary.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not _is_link_or_reparse(current)
        and stat.S_ISREG(current.st_mode)
        and _same_identity_and_type(created_stat, current)
    ):
        temporary.unlink()


def _path_is_link_or_reparse(path: Path) -> bool:
    return _is_link_or_reparse(path.stat(follow_symlinks=False))


def _validated_manifest_root(root: Path) -> Path:
    stat_result = root.stat(follow_symlinks=False)
    if _is_link_or_reparse(stat_result):
        raise OSError(f"manifest root is a filesystem link or reparse point: {root}")
    if not stat.S_ISDIR(stat_result.st_mode):
        raise OSError(f"manifest root is not a directory: {root}")
    return root


def _regular_files(root: Path) -> list[tuple[Path, os.stat_result]]:
    files: list[tuple[Path, os.stat_result]] = []
    for current, directory_names, file_names in os.walk(
        root,
        topdown=True,
        onerror=_raise_traversal_error,
        followlinks=False,
    ):
        current_path = Path(current)
        relative_current = current_path.relative_to(root)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name != ".git"
            and not _path_is_link_or_reparse(current_path / name)
        )
        for name in sorted(file_names):
            path = current_path / name
            relative = (relative_current / name).as_posix()
            if name == ".git" or relative == MANIFEST_NAME:
                continue
            stat_result = path.stat(follow_symlinks=False)
            if (
                not _is_link_or_reparse(stat_result)
                and stat.S_ISREG(stat_result.st_mode)
            ):
                files.append((path, stat_result))
    return sorted(files, key=lambda item: item[0].relative_to(root).as_posix())


def _raise_traversal_error(error: OSError) -> None:
    raise error


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
    files: list[FileDigest] = []
    for path, expected_stat in _regular_files(root_path):
        size_bytes, digest = _hash_regular_file(path, expected_stat)
        files.append(
            FileDigest(
                path=path.relative_to(root_path).as_posix(),
                size_bytes=size_bytes,
                sha256=digest,
            )
        )
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
