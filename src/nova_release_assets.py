"""Hash-bound, temporary model inputs for release verification, never Git content."""

from __future__ import annotations

from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from nova_release_worktree import (
    ReleasePathError, _CopyOperation, _absolute_input, _close_anchors,
    _entry_or_none, _inspect_candidate, _is_link_or_reparse,
    _open_candidate_from_temp, _open_chain, _open_directory_anchor,
    _open_source_file, _read_anchored_regular_file, _safe_destination,
    _same_identity_and_type, _source_stat, _verified_temp_root, git_output,
)


MANIFEST_NAME = "NOVA_RUNTIME_ASSETS.json"
_ROLES = (
    "left_hemisphere", "right_hemisphere", "memory_transformer",
    "planner_transformer", "critic_conscience_transformer",
    "dream_simulation_transformer", "speech_output_transformer",
)
_ALLOWED_PATHS = {
    f"checkpoints/brain_slots/{role}/{role}_v055_conversation_trained.pt"
    for role in _ROLES
}


class RuntimeAssetError(ValueError):
    """Required model input is unsafe, changed, or does not match its manifest."""


def _verify(root, asset: dict) -> None:
    before = _source_stat(root, asset["path"])
    descriptor, anchors = _open_source_file(root, _CopyOperation(asset["path"], before))
    digest = hashlib.sha256()
    try:
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
        if (
            not _same_identity_and_type(before, after)
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or after.st_size != asset["size_bytes"]
            or digest.hexdigest() != asset["sha256"]
        ):
            raise RuntimeAssetError("runtime asset does not match its committed manifest")
    finally:
        os.close(descriptor)
        _close_anchors(anchors)


class RuntimeAssets:
    def __init__(self, source: Path, candidate: Path, temp_root: Path) -> None:
        self.source = _absolute_input(source, "asset source")
        self.candidate = _absolute_input(candidate, "asset candidate")
        self.temp_root = temp_root
        self.files: list[dict] = []
        self.manifest_bytes: bytes | None = None
        anchor = _open_directory_anchor(self.candidate)
        try:
            if _entry_or_none(anchor, MANIFEST_NAME) is None:
                return
            self.manifest_bytes = _read_anchored_regular_file(anchor, MANIFEST_NAME)
            payload = json.loads(self.manifest_bytes)
            if payload.get("schema_version") != "1.0" or not isinstance(payload.get("files"), list):
                raise RuntimeAssetError("invalid runtime asset manifest schema")
            seen = set()
            for item in payload["files"]:
                if (
                    not isinstance(item, dict)
                    or item.get("path") not in _ALLOWED_PATHS
                    or item["path"] in seen
                    or type(item.get("size_bytes")) is not int
                    or not 0 < item["size_bytes"] <= 512 * 1024 * 1024
                    or not isinstance(item.get("sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
                ):
                    raise RuntimeAssetError("runtime asset manifest has an unapproved entry")
                seen.add(item["path"])
                self.files.append({key: item[key] for key in ("path", "size_bytes", "sha256")})
        except (OSError, ReleasePathError, json.JSONDecodeError) as error:
            raise RuntimeAssetError("cannot safely read runtime asset manifest") from error
        finally:
            anchor.close()

    def evidence(self) -> dict:
        return {
            "manifest": MANIFEST_NAME,
            "manifest_sha256": hashlib.sha256(self.manifest_bytes).hexdigest() if self.manifest_bytes is not None else None,
            "files": self.files,
        }

    @contextmanager
    def hydrated(self):
        if not self.files:
            yield
            return
        owned = []
        try:
            with ExitStack() as stack:
                if self.source.resolve() != self.source:
                    raise RuntimeAssetError("runtime asset source contains a filesystem link")
                source = _open_directory_anchor(self.source)
                stack.callback(source.close)
                temp_root, temp = _verified_temp_root(self.temp_root, self.source)
                stack.callback(temp.close)
                _, parts = _safe_destination(self.candidate, temp_root)
                candidate, candidate_anchors = _open_candidate_from_temp(temp, parts)
                stack.callback(_close_anchors, candidate_anchors)
                if _read_anchored_regular_file(candidate, MANIFEST_NAME) != self.manifest_bytes:
                    raise RuntimeAssetError("runtime asset manifest changed")
                # Complete preflight before creating any copies.
                for asset in self.files:
                    path = asset["path"]
                    _verify(source, asset)
                    if _inspect_candidate(candidate, path)[0] != "missing":
                        raise RuntimeAssetError("runtime asset destination already exists")
                    if git_output(self.candidate, "ls-files", "--", path):
                        raise RuntimeAssetError("runtime assets must not be tracked")
                    if git_output(self.candidate, "check-ignore", "--no-index", "--", path) != path:
                        raise RuntimeAssetError("runtime assets must be ignored by Git")
                try:
                    for asset in self.files:
                        parts = tuple(asset["path"].split("/"))
                        parents = _open_chain(candidate, parts[:-1], create=True)
                        # Keep destination directory handles pinned through cleanup.
                        stack.callback(_close_anchors, parents)
                        parent = parents[-1]
                        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                        fd = parent.open_file(parts[-1], flags, 0o600)
                        owned.append((parent, parts[-1], os.fstat(fd)))
                        try:
                            source_fd, source_parents = _open_source_file(source, _CopyOperation(asset["path"], _source_stat(source, asset["path"])))
                            try:
                                while block := os.read(source_fd, 1024 * 1024):
                                    view = memoryview(block)
                                    while view:
                                        view = view[os.write(fd, view):]
                                os.fsync(fd)
                            finally:
                                os.close(source_fd)
                                _close_anchors(source_parents)
                        finally:
                            os.close(fd)
                        _verify(source, asset)
                        _verify(candidate, asset)
                    try:
                        yield
                    finally:
                        if _read_anchored_regular_file(candidate, MANIFEST_NAME) != self.manifest_bytes:
                            raise RuntimeAssetError("runtime asset manifest changed during gates")
                        for asset in self.files:
                            _verify(source, asset)
                            _verify(candidate, asset)
                finally:
                    cleanup_error = None
                    for parent, name, created in reversed(owned):
                        try:
                            parent.validate_path()
                            current = parent.stat_entry(name)
                            if _is_link_or_reparse(current) or not stat.S_ISREG(current.st_mode) or not _same_identity_and_type(created, current):
                                raise RuntimeAssetError("runtime asset copy was replaced; refusing cleanup")
                            parent.unlink_entry(name)
                        except (OSError, ReleasePathError, RuntimeAssetError) as error:
                            cleanup_error = error
                    if cleanup_error is not None:
                        raise RuntimeAssetError("runtime asset cleanup failed safely") from cleanup_error
        except (OSError, ReleasePathError) as error:
            raise RuntimeAssetError("runtime asset hydration failed safely") from error
