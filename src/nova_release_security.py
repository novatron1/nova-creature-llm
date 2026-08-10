"""Release-content and dependency supply-chain checks for Nova."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import re
import stat
from typing import Iterable


RELEASE_SECURITY_VERSION = "1.0"
FORBIDDEN_NAMES = {
    ".env",
    ".nova_llm_config",
    "id_rsa",
    "id_dsa",
    "id_ed25519",
    "credentials.json",
}
FORBIDDEN_SUFFIXES = {".map", ".pem", ".key", ".p12", ".pfx"}
TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".txt",
    ".html",
    ".css",
    ".sh",
    ".ps1",
    ".bat",
}
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


@dataclass
class ReleaseSecurityResult:
    passed: bool
    inspected_files: int
    unexpected_files: list[str] = field(default_factory=list)
    secret_findings: list[str] = field(default_factory=list)
    oversized_debug_artifacts: list[str] = field(default_factory=list)
    path_escape_findings: list[str] = field(default_factory=list)
    version: str = RELEASE_SECURITY_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _record_path_escape(path: Path, base: Path, findings: list[str]) -> None:
    relative = path.relative_to(base).as_posix()
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        findings.append(relative)
        return
    if not resolved.is_relative_to(base):
        findings.append(relative)


def inspect_release(
    root: str | Path,
    *,
    max_debug_bytes: int = 5_000_000,
    ignored_directories: Iterable[str] = (),
) -> ReleaseSecurityResult:
    base = Path(root).resolve()
    if not base.is_dir():
        raise NotADirectoryError(base)
    ignored = {str(item).lower() for item in ignored_directories}
    unexpected: list[str] = []
    secrets: list[str] = []
    oversized: list[str] = []
    path_escapes: list[str] = []
    inspected = 0
    for current_root, directory_names, file_names in os.walk(base, followlinks=False):
        current = Path(current_root)
        directory_names.sort()
        file_names.sort()
        traversable_directories: list[str] = []
        for directory_name in directory_names:
            path = current / directory_name
            relative = path.relative_to(base)
            if any(part.lower() in ignored for part in relative.parts):
                continue
            if _is_link(path):
                _record_path_escape(path, base, path_escapes)
                continue
            traversable_directories.append(directory_name)
        directory_names[:] = traversable_directories
        for file_name in file_names:
            path = current / file_name
            relative = path.relative_to(base)
            if any(part.lower() in ignored for part in relative.parts[:-1]):
                continue
            if _is_link(path):
                _record_path_escape(path, base, path_escapes)
                continue
            if not path.is_file():
                continue
            inspected += 1
            lowered_name = path.name.lower()
            lowered_parts = {part.lower() for part in relative.parts}
            if (
                lowered_name in FORBIDDEN_NAMES
                or path.suffix.lower() in FORBIDDEN_SUFFIXES
                or "__pycache__" in lowered_parts
                or path.suffix.lower() in {".pyc", ".pyo"}
            ):
                unexpected.append(relative.as_posix())
            if path.stat().st_size > max_debug_bytes and any(
                marker in lowered_name for marker in ("debug", "trace", "log", "dump")
            ):
                oversized.append(relative.as_posix())
            if path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size <= 2_000_000:
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if any(pattern.search(content) for pattern in SECRET_PATTERNS):
                    secrets.append(relative.as_posix())
    return ReleaseSecurityResult(
        passed=not (unexpected or secrets or oversized or path_escapes),
        inspected_files=inspected,
        unexpected_files=sorted(set(unexpected)),
        secret_findings=sorted(set(secrets)),
        oversized_debug_artifacts=sorted(set(oversized)),
        path_escape_findings=sorted(set(path_escapes)),
    )


def verify_lockfile(lockfile: str | Path) -> dict:
    path = Path(lockfile)
    mismatches: list[dict[str, str]] = []
    checked = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
        if not match:
            mismatches.append({"requirement": line, "status": "not_exactly_pinned"})
            continue
        package, expected = match.groups()
        checked += 1
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError:
            actual = "not-installed"
        if actual != expected:
            mismatches.append(
                {
                    "requirement": line,
                    "status": "version_mismatch",
                    "actual": actual,
                }
            )
    return {"passed": not mismatches, "checked": checked, "mismatches": mismatches}


def generate_sbom(output: str | Path) -> dict:
    components = sorted(
        (
            {"name": distribution.metadata.get("Name") or distribution.name, "version": distribution.version}
            for distribution in metadata.distributions()
        ),
        key=lambda item: item["name"].lower(),
    )
    document = {
        "bomFormat": "CycloneDX-compatible",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:nova-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "component": {"name": "NOVA LLM CREATURE DESKTOP", "type": "application"},
            "telemetry_enabled": False,
        },
        "components": components,
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return document


def _main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a Nova release candidate")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("root")
    lock = subparsers.add_parser("verify-lock")
    lock.add_argument("path")
    sbom = subparsers.add_parser("sbom")
    sbom.add_argument("output")
    args = parser.parse_args()
    if args.command == "check":
        result = inspect_release(args.root).to_dict()
    elif args.command == "verify-lock":
        result = verify_lockfile(args.path)
    else:
        result = generate_sbom(args.output)
    print(json.dumps(result, indent=2))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(_main())
