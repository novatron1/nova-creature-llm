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


def _make_directory_link(link: Path, target: Path) -> None:
    if os.name != "nt":
        link.symlink_to(target, target_is_directory=True)
        return
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"directory link creation is unavailable: {result.stderr or result.stdout}")


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


def test_sha256_file_rejects_replacement_between_inspection_and_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "payload.txt"
    target.write_text("trusted", encoding="utf-8")
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("replaced", encoding="utf-8")
    real_open = os.open

    def replace_then_open(path: str | bytes | os.PathLike[str], flags: int, *args: int) -> int:
        if Path(path) == target:
            os.replace(replacement, target)
        return real_open(path, flags, *args)

    monkeypatch.setattr(release_manifest_module.os, "open", replace_then_open)

    with pytest.raises(OSError, match="file identity changed"):
        sha256_file(target)


def test_manifest_rejects_file_replacement_before_descriptor_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    target = candidate / "nova.py"
    target.write_text("trusted = True\n", encoding="utf-8")
    replacement = tmp_path / "replacement.py"
    replacement.write_text("trusted = False\n", encoding="utf-8")
    real_open = os.open

    def replace_then_open(path: str | bytes | os.PathLike[str], flags: int, *args: int) -> int:
        if Path(path) == target:
            os.replace(replacement, target)
        return real_open(path, flags, *args)

    monkeypatch.setattr(release_manifest_module.os, "open", replace_then_open)

    with pytest.raises(OSError, match="file identity changed"):
        build_content_manifest(
            candidate,
            source_branch="codex/test",
            source_commit="f" * 40,
            candidate_branch="codex/release-lock-test",
            excluded_counts={},
            deletions=[],
            gates={},
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


def test_manifest_skips_nested_git_administrative_pointer_file(tmp_path: Path) -> None:
    module = tmp_path / "vendor" / "module"
    module.mkdir(parents=True)
    (module / ".git").write_text("gitdir: ../../../modules/module\n", encoding="utf-8")
    (module / "library.py").write_text("value = 1\n", encoding="utf-8")

    manifest = build_content_manifest(
        tmp_path,
        source_branch="codex/test",
        source_commit="d" * 40,
        candidate_branch="codex/release-lock-test",
        excluded_counts={},
        deletions=[],
        gates={},
    )

    assert [item.path for item in manifest.files] == ["vendor/module/library.py"]


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


def test_manifest_rejects_linked_root(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "nova.py").write_text("answer = 42\n", encoding="utf-8")
    linked_root = tmp_path / "linked-candidate"
    _make_directory_link(linked_root, candidate)

    with pytest.raises(OSError, match="manifest root.*link"):
        build_content_manifest(
            linked_root,
            source_branch="codex/test",
            source_commit="f" * 40,
            candidate_branch="codex/release-lock-test",
            excluded_counts={},
            deletions=[],
            gates={},
        )


def test_manifest_fails_closed_on_directory_enumeration_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "secret.txt").write_text("private", encoding="utf-8")
    real_scandir = os.scandir

    def deny_blocked_directory(path: str | bytes | os.PathLike[str]):
        if Path(path) == blocked:
            raise PermissionError("injected traversal denial")
        return real_scandir(path)

    monkeypatch.setattr(release_manifest_module.os, "scandir", deny_blocked_directory)

    with pytest.raises(PermissionError, match="injected traversal denial"):
        build_content_manifest(
            tmp_path,
            source_branch="codex/test",
            source_commit="f" * 40,
            candidate_branch="codex/release-lock-test",
            excluded_counts={},
            deletions=[],
            gates={},
        )


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
    git_common_dir.mkdir()
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


def test_release_state_root_rejects_linked_git_common_directory(
    tmp_path: Path,
) -> None:
    real_common_dir = tmp_path / "repo.git"
    real_common_dir.mkdir()
    linked_common_dir = tmp_path / "linked-repo.git"
    _make_directory_link(linked_common_dir, real_common_dir)

    with pytest.raises(OSError, match="Git common directory.*link"):
        release_manifest_module.release_state_root(linked_common_dir)


def test_release_state_root_rejects_linked_state_directory(tmp_path: Path) -> None:
    git_common_dir = tmp_path / "repo.git"
    git_common_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _make_directory_link(git_common_dir / "nova-release-lock", outside)

    with pytest.raises(OSError, match="release state root.*link"):
        release_manifest_module.release_state_root(git_common_dir)


def test_atomic_write_rejects_linked_report_parent(tmp_path: Path) -> None:
    git_common_dir = tmp_path / "repo.git"
    git_common_dir.mkdir()
    state_root = release_manifest_module.release_state_root(git_common_dir)
    state_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _make_directory_link(state_root / "runs", outside)
    report_path = state_root / "runs" / "run-001.json"

    with pytest.raises(OSError, match="release state path.*link"):
        release_manifest_module.write_json_atomic(report_path, {"status": "running"})

    assert not (outside / "run-001.json").exists()


def test_atomic_write_refuses_preexisting_temporary_entry(tmp_path: Path) -> None:
    git_common_dir = tmp_path / "repo.git"
    git_common_dir.mkdir()
    report_path = (
        release_manifest_module.release_state_root(git_common_dir)
        / "runs"
        / "run-001.json"
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text('{"old":true}\n', encoding="utf-8")
    temporary = report_path.with_name("run-001.json.tmp")
    temporary.write_text("untrusted temporary content", encoding="utf-8")

    with pytest.raises(FileExistsError):
        release_manifest_module.write_json_atomic(report_path, {"status": "running"})

    assert temporary.read_text(encoding="utf-8") == "untrusted temporary content"
    assert report_path.read_text(encoding="utf-8") == '{"old":true}\n'


def test_atomic_write_refuses_preexisting_temporary_link(tmp_path: Path) -> None:
    git_common_dir = tmp_path / "repo.git"
    git_common_dir.mkdir()
    report_path = (
        release_manifest_module.release_state_root(git_common_dir)
        / "runs"
        / "run-001.json"
    )
    report_path.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel.txt").write_text("outside", encoding="utf-8")
    temporary = report_path.with_name("run-001.json.tmp")
    _make_directory_link(temporary, outside)

    with pytest.raises(OSError):
        release_manifest_module.write_json_atomic(report_path, {"status": "running"})

    assert (outside / "sentinel.txt").read_text(encoding="utf-8") == "outside"
    if os.name == "nt":
        assert temporary.stat(follow_symlinks=False).st_file_attributes & (
            stat.FILE_ATTRIBUTE_REPARSE_POINT
        )
    else:
        assert temporary.is_symlink()


def test_atomic_write_cleans_owned_temporary_after_fsync_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git_common_dir = tmp_path / "repo.git"
    git_common_dir.mkdir()
    report_path = (
        release_manifest_module.release_state_root(git_common_dir)
        / "runs"
        / "run-001.json"
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text('{"old":true}\n', encoding="utf-8")
    temporary = report_path.with_name("run-001.json.tmp")

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("injected fsync failure")

    monkeypatch.setattr(release_manifest_module.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="injected fsync failure"):
        release_manifest_module.write_json_atomic(report_path, {"status": "running"})

    assert not temporary.exists()
    assert report_path.read_text(encoding="utf-8") == '{"old":true}\n'


def test_atomic_write_leaves_no_temporary_after_serialization_failure(
    tmp_path: Path,
) -> None:
    git_common_dir = tmp_path / "repo.git"
    git_common_dir.mkdir()
    state_root = release_manifest_module.release_state_root(git_common_dir)
    report_path = state_root / "runs" / "run-001.json"
    temporary = report_path.with_name("run-001.json.tmp")

    with pytest.raises(TypeError):
        release_manifest_module.write_json_atomic(report_path, {"bad": object()})

    assert not temporary.exists()
    assert not state_root.exists()


def test_atomic_write_cleans_owned_temporary_after_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git_common_dir = tmp_path / "repo.git"
    git_common_dir.mkdir()
    report_path = (
        release_manifest_module.release_state_root(git_common_dir)
        / "runs"
        / "run-001.json"
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text('{"old":true}\n', encoding="utf-8")
    temporary = report_path.with_name("run-001.json.tmp")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(release_manifest_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        release_manifest_module.write_json_atomic(report_path, {"status": "running"})

    assert not temporary.exists()
    assert report_path.read_text(encoding="utf-8") == '{"old":true}\n'
