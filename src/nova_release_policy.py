"""Deterministic, fail-closed classification for release snapshots."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass, field, replace
from enum import Enum
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Iterable


class SnapshotClass(str, Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class SnapshotDecision:
    path: str
    classification: SnapshotClass
    rule: str
    tracked: bool = False
    change: str = "present"
    size_bytes: int = 0


@dataclass
class SnapshotReport:
    schema_version: str
    decisions: list[SnapshotDecision] = field(default_factory=list)

    @property
    def included(self) -> list[SnapshotDecision]:
        return [item for item in self.decisions if item.classification is SnapshotClass.INCLUDE]

    @property
    def excluded(self) -> list[SnapshotDecision]:
        return [item for item in self.decisions if item.classification is SnapshotClass.EXCLUDE]

    @property
    def ambiguous(self) -> list[SnapshotDecision]:
        return [item for item in self.decisions if item.classification is SnapshotClass.AMBIGUOUS]

    @property
    def passed(self) -> bool:
        return not self.ambiguous


_TEXT_SUFFIXES = frozenset(
    {
        ".bat",
        ".cfg",
        ".cjs",
        ".conf",
        ".css",
        ".csv",
        ".gql",
        ".graphql",
        ".htm",
        ".html",
        ".ini",
        ".js",
        ".json",
        ".jsonl",
        ".jsx",
        ".less",
        ".lock",
        ".md",
        ".mjs",
        ".properties",
        ".ps1",
        ".py",
        ".pyi",
        ".rst",
        ".sass",
        ".scss",
        ".sh",
        ".sql",
        ".svg",
        ".toml",
        ".ts",
        ".tsv",
        ".tsx",
        ".txt",
        ".webmanifest",
        ".xml",
        ".yaml",
        ".yml",
    }
)


def _normalize_path(path: str | os.PathLike[str]) -> str:
    return os.fspath(path).replace("\\", "/")


def _is_workspace_relative(path: str) -> bool:
    if not path or path.startswith("/") or re.match(r"^[A-Za-z]:($|/)", path):
        return False
    return ".." not in PurePosixPath(path).parts


@lru_cache(maxsize=None)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    expression: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    expression.append("(?:.*/)?")
                    index += 1
                else:
                    expression.append(".*")
                continue
            expression.append("[^/]*")
        elif character == "?":
            expression.append("[^/]")
        else:
            expression.append(re.escape(character))
        index += 1
    expression.append("$")
    return re.compile("".join(expression))


@dataclass(frozen=True)
class SnapshotPolicy:
    schema_version: str
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    ambiguous: tuple[str, ...]
    allowed_binary_suffixes: frozenset[str]
    max_static_asset_bytes: int
    required_files: tuple[str, ...] = ()

    @classmethod
    def load(cls, path: Path) -> SnapshotPolicy:
        payload = json.loads(path.read_text(encoding="utf-8"))
        required_files = tuple(
            _normalize_path(item) for item in payload.get("required_files", [])
        )
        if any(
            not _is_workspace_relative(item)
            or any(marker in item for marker in ("*", "?", "[", "]"))
            for item in required_files
        ):
            raise ValueError("required_files must contain exact workspace-relative paths")
        return cls(
            schema_version=str(payload["schema_version"]),
            include=tuple(payload["include"]),
            exclude=tuple(payload["exclude"]),
            ambiguous=tuple(payload["ambiguous"]),
            allowed_binary_suffixes=frozenset(
                str(suffix).lower() for suffix in payload["allowed_binary_suffixes"]
            ),
            max_static_asset_bytes=int(payload["max_static_asset_bytes"]),
            required_files=required_files,
        )

    @staticmethod
    def _matching_rule(path: str, rules: Iterable[str]) -> str | None:
        candidates = (path, f"{path}/")
        for rule in rules:
            matcher = _glob_regex(rule.replace("\\", "/"))
            if any(matcher.fullmatch(candidate) for candidate in candidates):
                return rule
        return None

    def classify(
        self,
        path: str | os.PathLike[str],
        size_bytes: int = 0,
        is_link: bool = False,
    ) -> SnapshotDecision:
        normalized = _normalize_path(path)
        if not _is_workspace_relative(normalized):
            return SnapshotDecision(
                normalized,
                SnapshotClass.AMBIGUOUS,
                "path_outside_workspace",
                size_bytes=size_bytes,
            )

        if normalized in self.required_files:
            if is_link:
                return SnapshotDecision(
                    normalized,
                    SnapshotClass.AMBIGUOUS,
                    "filesystem_link_requires_boundary_check",
                    size_bytes=size_bytes,
                )
            suffix = PurePosixPath(normalized).suffix.lower()
            if suffix and suffix not in _TEXT_SUFFIXES and suffix not in self.allowed_binary_suffixes:
                return SnapshotDecision(
                    normalized,
                    SnapshotClass.AMBIGUOUS,
                    "binary_suffix_not_allowed",
                    size_bytes=size_bytes,
                )
            if suffix in self.allowed_binary_suffixes and size_bytes > self.max_static_asset_bytes:
                return SnapshotDecision(
                    normalized,
                    SnapshotClass.AMBIGUOUS,
                    "static_asset_too_large",
                    size_bytes=size_bytes,
                )
            return SnapshotDecision(
                normalized,
                SnapshotClass.INCLUDE,
                "required_files",
                size_bytes=size_bytes,
            )

        excluded_rule = self._matching_rule(normalized, self.exclude)
        if excluded_rule is not None:
            return SnapshotDecision(
                normalized,
                SnapshotClass.EXCLUDE,
                excluded_rule,
                size_bytes=size_bytes,
            )

        if is_link:
            return SnapshotDecision(
                normalized,
                SnapshotClass.AMBIGUOUS,
                "filesystem_link_requires_boundary_check",
                size_bytes=size_bytes,
            )

        ambiguous_rule = self._matching_rule(normalized, self.ambiguous)
        if ambiguous_rule is not None:
            return SnapshotDecision(
                normalized,
                SnapshotClass.AMBIGUOUS,
                ambiguous_rule,
                size_bytes=size_bytes,
            )

        suffix = PurePosixPath(normalized).suffix.lower()
        if suffix and suffix not in _TEXT_SUFFIXES and suffix not in self.allowed_binary_suffixes:
            return SnapshotDecision(
                normalized,
                SnapshotClass.AMBIGUOUS,
                "binary_suffix_not_allowed",
                size_bytes=size_bytes,
            )

        if suffix in self.allowed_binary_suffixes and size_bytes > self.max_static_asset_bytes:
            return SnapshotDecision(
                normalized,
                SnapshotClass.AMBIGUOUS,
                "static_asset_too_large",
                size_bytes=size_bytes,
            )

        included_rule = self._matching_rule(normalized, self.include)
        if included_rule is not None:
            return SnapshotDecision(
                normalized,
                SnapshotClass.INCLUDE,
                included_rule,
                size_bytes=size_bytes,
            )

        return SnapshotDecision(
            normalized,
            SnapshotClass.AMBIGUOUS,
            "no_policy_rule",
            size_bytes=size_bytes,
        )


def _is_link_or_reparse(stat_result: os.stat_result) -> bool:
    if stat.S_ISLNK(stat_result.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(reparse_flag and file_attributes & reparse_flag)


def _normalized_paths(paths: Iterable[str | os.PathLike[str]]) -> set[str]:
    return {_normalize_path(path) for path in paths}


def scan_workspace(
    repo_root: Path,
    policy: SnapshotPolicy,
    tracked_paths: Iterable[str | os.PathLike[str]],
    deleted_paths: Iterable[str | os.PathLike[str]],
) -> SnapshotReport:
    repo_root = Path(repo_root)
    tracked = _normalized_paths(tracked_paths)
    deleted = _normalized_paths(deleted_paths)
    decisions: dict[str, SnapshotDecision] = {}

    for current_root, directories, files in os.walk(repo_root, topdown=True, followlinks=False):
        current = Path(current_root)
        directories.sort()
        files.sort()

        retained_directories: list[str] = []
        for directory_name in directories:
            directory_path = current / directory_name
            relative_path = directory_path.relative_to(repo_root).as_posix()
            stat_result = directory_path.lstat()
            is_link = _is_link_or_reparse(stat_result)
            decision = policy.classify(relative_path, size_bytes=stat_result.st_size, is_link=is_link)
            if is_link:
                decisions[relative_path] = replace(
                    decision,
                    tracked=relative_path in tracked,
                )
                continue
            if decision.classification is not SnapshotClass.EXCLUDE:
                retained_directories.append(directory_name)
        directories[:] = retained_directories

        for file_name in files:
            file_path = current / file_name
            relative_path = file_path.relative_to(repo_root).as_posix()
            stat_result = file_path.lstat()
            decision = policy.classify(
                relative_path,
                size_bytes=stat_result.st_size,
                is_link=_is_link_or_reparse(stat_result),
            )
            decisions[relative_path] = replace(
                decision,
                tracked=relative_path in tracked,
            )

    for deleted_path in deleted:
        decision = policy.classify(deleted_path, size_bytes=0, is_link=False)
        decisions[deleted_path] = replace(
            decision,
            tracked=deleted_path in tracked,
            change="deleted",
        )

    resolved_root = repo_root.resolve()
    for required_path in policy.required_files:
        if required_path in decisions:
            continue
        file_path = repo_root / Path(required_path)
        if not file_path.exists():
            continue
        try:
            stat_result = file_path.lstat()
            resolved_path = file_path.resolve(strict=True)
        except OSError:
            decisions[required_path] = SnapshotDecision(
                required_path,
                SnapshotClass.AMBIGUOUS,
                "required_file_unreadable",
                tracked=required_path in tracked,
            )
            continue
        if not resolved_path.is_relative_to(resolved_root):
            decisions[required_path] = SnapshotDecision(
                required_path,
                SnapshotClass.AMBIGUOUS,
                "path_outside_workspace",
                tracked=required_path in tracked,
                size_bytes=stat_result.st_size,
            )
            continue
        if not stat.S_ISREG(stat_result.st_mode):
            decisions[required_path] = SnapshotDecision(
                required_path,
                SnapshotClass.AMBIGUOUS,
                "required_file_not_regular",
                tracked=required_path in tracked,
                size_bytes=stat_result.st_size,
            )
            continue
        decision = policy.classify(
            required_path,
            size_bytes=stat_result.st_size,
            is_link=_is_link_or_reparse(stat_result),
        )
        decisions[required_path] = replace(
            decision,
            tracked=required_path in tracked,
        )

    return SnapshotReport(
        schema_version=policy.schema_version,
        decisions=[decisions[path] for path in sorted(decisions)],
    )
