from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

import nova_release_security
from nova_release_security import generate_sbom, inspect_release, verify_lockfile


def _create_directory_link(target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        if os.name != "nt":
            pytest.skip("filesystem links are unavailable for this user")
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
        )
        if junction.returncode:
            pytest.skip("filesystem links are unavailable for this user")


def test_clean_release_candidate_passes(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('nova')", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"nova"}', encoding="utf-8")

    result = inspect_release(tmp_path)
    assert result.passed
    assert result.inspected_files == 2


def test_release_rejects_source_maps_secrets_private_keys_and_debug_artifacts(tmp_path: Path) -> None:
    (tmp_path / "app.js.map").write_text("{}", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=true", encoding="utf-8")
    (tmp_path / "code.py").write_text(
        'api_key = "sk-abcdefghijklmnopqrstuvwxyz012345"',
        encoding="utf-8",
    )
    (tmp_path / "private.pem").write_text(
        "-----BEGIN PRIVATE KEY-----\nabc",
        encoding="utf-8",
    )
    (tmp_path / "debug.log").write_bytes(b"x" * 1024)

    result = inspect_release(tmp_path, max_debug_bytes=512)
    assert not result.passed
    assert "app.js.map" in result.unexpected_files
    assert ".env" in result.unexpected_files
    assert "private.pem" in result.unexpected_files
    assert "code.py" in result.secret_findings
    assert "debug.log" in result.oversized_debug_artifacts


def test_release_rejects_link_that_resolves_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("private", encoding="utf-8")
    link = tmp_path / "outside-link.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        if os.name != "nt":
            pytest.skip("filesystem links are unavailable for this user")
        outside.unlink()
        outside.mkdir()
        (outside / "private.txt").write_text("private", encoding="utf-8")
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True,
            check=False,
        )
        if junction.returncode:
            pytest.skip("filesystem links are unavailable for this user")

    result = inspect_release(tmp_path)

    assert not result.passed
    assert result.path_escape_findings == ["outside-link.txt"]


def test_release_rejects_ignored_directory_link_that_resolves_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-ignored-outside"
    outside.mkdir()
    (outside / "private.txt").write_text("private", encoding="utf-8")
    link = tmp_path / "ignored"
    _create_directory_link(outside, link)

    result = inspect_release(tmp_path, ignored_directories=("ignored",))

    assert not result.passed
    assert result.path_escape_findings == ["ignored"]


def test_release_fails_closed_when_directory_cannot_be_enumerated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    real_scandir = os.scandir

    def failing_scandir(path: str | os.PathLike[str]):
        if Path(path) == blocked:
            raise PermissionError(13, "blocked for test", blocked)
        return real_scandir(path)

    monkeypatch.setattr(nova_release_security.os, "scandir", failing_scandir)

    result = inspect_release(tmp_path)

    assert not result.passed
    assert result.path_escape_findings == ["blocked"]


def test_release_fails_closed_when_entry_cannot_be_classified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unclassifiable = tmp_path / "unclassifiable.txt"
    unclassifiable.write_text("private", encoding="utf-8")
    real_lstat = os.lstat

    def failing_lstat(path, *args, **kwargs):
        if Path(path) == unclassifiable:
            raise PermissionError(13, "blocked for test", unclassifiable)
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(nova_release_security.os, "lstat", failing_lstat)

    result = inspect_release(tmp_path)

    assert not result.passed
    assert result.path_escape_findings == ["unclassifiable.txt"]


def test_exact_dependency_lock_is_verified(tmp_path: Path) -> None:
    lock = tmp_path / "runtime.lock"
    lock.write_text("definitely-not-installed==1.2.3\nunpinned>=1\n", encoding="utf-8")

    result = verify_lockfile(lock)
    assert not result["passed"]
    assert len(result["mismatches"]) == 2


def test_sbom_is_machine_readable_and_disables_telemetry(tmp_path: Path) -> None:
    output = tmp_path / "sbom.json"
    result = generate_sbom(output)
    loaded = json.loads(output.read_text(encoding="utf-8"))

    assert result["bomFormat"] == "CycloneDX-compatible"
    assert loaded["metadata"]["telemetry_enabled"] is False
    assert isinstance(loaded["components"], list)
