from dataclasses import asdict
import os
from pathlib import Path
import stat
import subprocess

import nova_release_manifest as release_manifest_module
import pytest
from nova_release_manifest import (
    build_content_manifest,
    canonical_json,
    sha256_file,
)


def test_manifest_is_stable_and_excludes_itself(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "nova.py").write_text("answer = 42\n", encoding="utf-8")
    manifest_path = tmp_path / "NOVA_RELEASE_MANIFEST.json"
    manifest_path.write_text('{"old": true}', encoding="utf-8")

    first = build_content_manifest(
        tmp_path,
        source_branch="codex/nova-live-app-fixes",
        source_commit="a" * 40,
        candidate_branch="codex/release-lock-test",
        excluded_counts={"private_data": 3},
        deletions=["src/removed.py"],
        gates={"python_full": True},
    )
    second = build_content_manifest(
        tmp_path,
        source_branch="codex/nova-live-app-fixes",
        source_commit="a" * 40,
        candidate_branch="codex/release-lock-test",
        excluded_counts={"private_data": 3},
        deletions=["src/removed.py"],
        gates={"python_full": True},
    )

    assert canonical_json(first.to_dict()) == canonical_json(second.to_dict())
    assert [item.path for item in first.files] == ["src/nova.py"]
    assert first.release_id == second.release_id


def test_manifest_changes_when_file_content_changes(tmp_path: Path) -> None:
    target = tmp_path / "nova.py"
    target.write_text("one", encoding="utf-8")
    first = build_content_manifest(
        tmp_path,
        source_branch="codex/test",
        source_commit="a" * 40,
        candidate_branch="codex/release-lock-test",
        excluded_counts={},
        deletions=[],
        gates={"python_full": True},
    )
    target.write_text("two", encoding="utf-8")
    second = build_content_manifest(
        tmp_path,
        source_branch="codex/test",
        source_commit="a" * 40,
        candidate_branch="codex/release-lock-test",
        excluded_counts={},
        deletions=[],
        gates={"python_full": True},
    )
    assert first.release_id != second.release_id
    assert first.files[0].sha256 != second.files[0].sha256


def test_canonical_json_and_manifest_collections_are_sorted(tmp_path: Path) -> None:
    (tmp_path / "z.txt").write_text("z", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    manifest = build_content_manifest(
        tmp_path,
        source_branch="codex/test",
        source_commit="b" * 40,
        candidate_branch="codex/release-lock-test",
        excluded_counts={"z_private": 2, "a_cache": 1},
        deletions=["z/old.py", "a/old.py"],
        gates={"z_gate": False, "a_gate": True},
    )

    assert canonical_json({"z": "é", "a": [{"b": 2, "a": 1}]}) == (
        '{"a":[{"a":1,"b":2}],"z":"é"}\n'
    )
    assert [item.path for item in manifest.files] == ["a.txt", "z.txt"]
    assert manifest.excluded_counts == {"a_cache": 1, "z_private": 2}
    assert manifest.deletions == ["a/old.py", "z/old.py"]
    assert [(item.name, item.passed) for item in manifest.gates] == [
        ("a_gate", True),
        ("z_gate", False),
    ]
    assert set(manifest.to_dict()) == {
        "candidate_branch",
        "deletions",
        "excluded_counts",
        "files",
        "gates",
        "release_id",
        "schema_version",
        "source_branch",
        "source_commit",
    }
    assert manifest.release_id.startswith("b" * 40 + "-")
    assert len(manifest.release_id) == 40 + 1 + 64


def test_release_id_is_source_commit_plus_canonical_content_digest(
    tmp_path: Path,
) -> None:
    manifest = build_content_manifest(
        tmp_path,
        source_branch="source",
        source_commit="a" * 40,
        candidate_branch="candidate",
        excluded_counts={},
        deletions=[],
        gates={},
    )

    assert manifest.release_id == (
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-"
        "aa133b2f6b60bc6f36014c02ab29bcd9"
        "40f2a25b7759eb39b0ccd5ffd4fe4338"
    )


def test_sha256_file_uses_file_bytes(tmp_path: Path) -> None:
    target = tmp_path / "payload.bin"
    target.write_bytes(b"abc")

    assert sha256_file(target) == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_manifest_skips_git_administration_and_file_links(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    target = tmp_path / "target.txt"
    target.write_text("content", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(target)
    except OSError:
        link = None

    manifest = build_content_manifest(
        tmp_path,
        source_branch="codex/test",
        source_commit="c" * 40,
        candidate_branch="codex/release-lock-test",
        excluded_counts={},
        deletions=[],
        gates={},
    )

    assert [item.path for item in manifest.files] == ["target.txt"]
    if link is not None:
        assert "linked.txt" not in [item.path for item in manifest.files]


def test_manifest_skips_git_administrative_pointer_file(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("gitdir: ../repo.git/worktrees/candidate\n", encoding="utf-8")
    (tmp_path / "nova.py").write_text("answer = 42\n", encoding="utf-8")

    manifest = build_content_manifest(
        tmp_path,
        source_branch="codex/test",
        source_commit="d" * 40,
        candidate_branch="codex/release-lock-test",
        excluded_counts={},
        deletions=[],
        gates={},
    )

    assert [item.path for item in manifest.files] == ["nova.py"]


@pytest.mark.skipif(os.name != "nt", reason="Windows junction coverage")
def test_manifest_does_not_follow_windows_junction(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    external_target = tmp_path / "external"
    external_target.mkdir()
    (external_target / "sentinel.txt").write_text("private", encoding="utf-8")
    junction = candidate / "linked"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(external_target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"junction creation is not supported: {result.stderr or result.stdout}")
    assert junction.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT

    manifest = build_content_manifest(
        candidate,
        source_branch="codex/test",
        source_commit="e" * 40,
        candidate_branch="codex/release-lock-test",
        excluded_counts={},
        deletions=[],
        gates={},
    )

    assert manifest.files == []


def test_run_report_is_local_to_git_common_dir_and_written_atomically(
    tmp_path: Path,
) -> None:
    run_report_type = release_manifest_module.RunReport
    release_state_root = release_manifest_module.release_state_root
    write_json_atomic = release_manifest_module.write_json_atomic
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "nova.py").write_text("answer = 42\n", encoding="utf-8")
    git_common_dir = candidate / ".git"
    report = run_report_type(
        schema_version="1.0",
        run_id="run-001",
        status="running",
        started_at="2026-08-10T12:00:00Z",
        source_commit="a" * 40,
        candidate_branch="codex/release-lock-test",
        gates=[{"name": "python_full", "passed": True}],
    )

    state_root = release_state_root(git_common_dir)
    report_path = state_root / "runs" / "run-001.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text('{"old":true}\n', encoding="utf-8")
    write_json_atomic(report_path, asdict(report))
    manifest = build_content_manifest(
        candidate,
        source_branch="codex/test",
        source_commit="a" * 40,
        candidate_branch="codex/release-lock-test",
        excluded_counts={},
        deletions=[],
        gates={},
    )

    assert state_root == git_common_dir / "nova-release-lock"
    assert report_path.read_text(encoding="utf-8") == (
        '{"candidate_branch":"codex/release-lock-test","candidate_commit":null,'
        '"failure_gate":null,"gates":[{"name":"python_full","passed":true}],'
        '"master_after":null,"master_before":null,"rollback_ref":null,'
        '"run_id":"run-001","schema_version":"1.0",'
        '"source_commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        '"started_at":"2026-08-10T12:00:00Z","status":"running"}\n'
    )
    assert not report_path.with_name("run-001.json.tmp").exists()
    assert report_path.is_relative_to(git_common_dir)
    assert [item.path for item in manifest.files] == ["nova.py"]
