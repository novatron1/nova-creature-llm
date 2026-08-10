import os
import stat
import subprocess
from pathlib import Path

import pytest

from nova_release_policy import SnapshotClass, SnapshotPolicy, scan_workspace


def test_exclusion_overrides_inclusion(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        """{
          "schema_version": "1.0",
          "include": ["src/**", "config/*.example.json"],
          "exclude": ["**/*.db", "config/*.local.json"],
          "ambiguous": ["src/private.*", "**/*.exe"],
          "allowed_binary_suffixes": [".png"],
          "max_static_asset_bytes": 5242880
        }""",
        encoding="utf-8",
    )
    policy = SnapshotPolicy.load(policy_path)

    assert policy.classify("src/nova.py", size_bytes=12).classification is SnapshotClass.INCLUDE
    overlapping = policy.classify("src/private.db", size_bytes=12)
    excluded_link = policy.classify("config/workflow.local.json", size_bytes=12, is_link=True)

    assert overlapping.classification is SnapshotClass.EXCLUDE
    assert overlapping.rule == "**/*.db"
    assert excluded_link.classification is SnapshotClass.EXCLUDE
    assert excluded_link.rule == "config/*.local.json"
    assert policy.classify("tools/cloudflared.exe", size_bytes=12).classification is SnapshotClass.AMBIGUOUS
    assert policy.classify("mystery.xyz", size_bytes=12).classification is SnapshotClass.AMBIGUOUS


def test_large_static_asset_and_link_fail_closed() -> None:
    policy = SnapshotPolicy.load(Path("config/nova_release_snapshot_policy.json"))

    large = policy.classify("assets/hero.png", size_bytes=5_242_881)
    linked = policy.classify("assets/hero.png", size_bytes=10, is_link=True)

    assert large.classification is SnapshotClass.AMBIGUOUS
    assert large.rule == "static_asset_too_large"
    assert linked.classification is SnapshotClass.AMBIGUOUS
    assert linked.rule == "filesystem_link_requires_boundary_check"


def test_unsafe_paths_fail_closed_and_separators_are_normalized(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        """{
          "schema_version": "1.0",
          "include": ["src/**"],
          "exclude": [],
          "ambiguous": [],
          "allowed_binary_suffixes": [],
          "max_static_asset_bytes": 5242880
        }""",
        encoding="utf-8",
    )
    policy = SnapshotPolicy.load(policy_path)

    normalized = policy.classify(r"src\nova.py", size_bytes=12)
    absolute = policy.classify(r"C:\outside\nova.py", size_bytes=12)
    traversal = policy.classify("src/../outside.py", size_bytes=12)

    assert normalized.path == "src/nova.py"
    assert normalized.classification is SnapshotClass.INCLUDE
    assert absolute.classification is SnapshotClass.AMBIGUOUS
    assert absolute.rule == "path_outside_workspace"
    assert traversal.classification is SnapshotClass.AMBIGUOUS
    assert traversal.rule == "path_outside_workspace"


def test_unapproved_binary_suffix_fails_closed(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        """{
          "schema_version": "1.0",
          "include": ["assets/**"],
          "exclude": [],
          "ambiguous": [],
          "allowed_binary_suffixes": [".png"],
          "max_static_asset_bytes": 5242880
        }""",
        encoding="utf-8",
    )
    policy = SnapshotPolicy.load(policy_path)

    decision = policy.classify("assets/payload.dat", size_bytes=12)

    assert decision.classification is SnapshotClass.AMBIGUOUS
    assert decision.rule == "binary_suffix_not_allowed"


def test_workspace_scan_is_sorted_and_preserves_tracked_deletion(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "z.py").write_text("z = 1", encoding="utf-8")
    (tmp_path / "src" / "a.py").write_text("a = 1", encoding="utf-8")
    policy = SnapshotPolicy.load(Path("config/nova_release_snapshot_policy.json"))

    report = scan_workspace(
        tmp_path,
        policy,
        tracked_paths={"src/a.py", "src/removed.py"},
        deleted_paths={"src/removed.py"},
    )

    assert [item.path for item in report.decisions] == [
        "src/a.py",
        "src/removed.py",
        "src/z.py",
    ]
    removed = next(item for item in report.decisions if item.path == "src/removed.py")
    assert removed.change == "deleted"
    assert removed.tracked is True


def test_workspace_scan_prunes_policy_excluded_directories(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "nova.py").write_text("nova = True", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "secret.txt").write_text("private", encoding="utf-8")
    policy = SnapshotPolicy.load(Path("config/nova_release_snapshot_policy.json"))

    report = scan_workspace(tmp_path, policy, tracked_paths=set(), deleted_paths=set())

    assert [item.path for item in report.decisions] == ["src/nova.py"]
    assert report.passed is True


def test_workspace_scan_records_directory_symlink_without_following(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    assets = repo_root / "assets"
    assets.mkdir(parents=True)
    external_target = tmp_path / "external"
    external_target.mkdir()
    (external_target / "sentinel.txt").write_text("must not be scanned", encoding="utf-8")
    linked_directory = assets / "linked"
    try:
        linked_directory.symlink_to(external_target, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks are not supported for this test user: {error}")
    policy = SnapshotPolicy.load(Path("config/nova_release_snapshot_policy.json"))

    report = scan_workspace(repo_root, policy, tracked_paths=set(), deleted_paths=set())

    paths = [item.path for item in report.decisions]
    assert paths == ["assets/linked"]
    assert report.decisions[0].classification is SnapshotClass.AMBIGUOUS
    assert report.decisions[0].rule == "filesystem_link_requires_boundary_check"
    assert "assets/linked/sentinel.txt" not in paths


@pytest.mark.skipif(os.name != "nt", reason="Windows junction coverage")
def test_workspace_scan_records_windows_junction_without_following(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    assets = repo_root / "assets"
    assets.mkdir(parents=True)
    external_target = tmp_path / "external-junction-target"
    external_target.mkdir()
    (external_target / "sentinel.txt").write_text("must not be scanned", encoding="utf-8")
    junction = assets / "junction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(external_target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"junction creation is not supported: {result.stderr or result.stdout}")
    assert junction.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    policy = SnapshotPolicy.load(Path("config/nova_release_snapshot_policy.json"))

    report = scan_workspace(repo_root, policy, tracked_paths=set(), deleted_paths=set())

    paths = [item.path for item in report.decisions]
    assert paths == ["assets/junction"]
    assert report.decisions[0].classification is SnapshotClass.AMBIGUOUS
    assert report.decisions[0].rule == "filesystem_link_requires_boundary_check"
    assert "assets/junction/sentinel.txt" not in paths
