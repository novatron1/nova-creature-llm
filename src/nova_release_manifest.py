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

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(_HASH_BLOCK_SIZE):
            digest.update(block)
    return digest.hexdigest()


def release_state_root(git_common_dir: str | os.PathLike[str]) -> Path:
    """Return the repository-local administrative root for release state."""

    return Path(git_common_dir) / "nova-release-lock"


def write_json_atomic(path: str | os.PathLike[str], value: object) -> None:
    """Durably write canonical JSON before atomically replacing ``path``."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def _is_link_or_reparse(stat_result: os.stat_result) -> bool:
    if stat.S_ISLNK(stat_result.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(reparse_flag and file_attributes & reparse_flag)


def _path_is_link_or_reparse(path: Path) -> bool:
    try:
        return _is_link_or_reparse(path.stat(follow_symlinks=False))
    except FileNotFoundError:
        return True


def _regular_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
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
            if relative in {".git", MANIFEST_NAME}:
                continue
            try:
                stat_result = path.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            if (
                not _is_link_or_reparse(stat_result)
                and stat.S_ISREG(stat_result.st_mode)
            ):
                files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


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

    root_path = Path(root)
    files = [
        FileDigest(
            path=path.relative_to(root_path).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path),
        )
        for path in _regular_files(root_path)
    ]
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
