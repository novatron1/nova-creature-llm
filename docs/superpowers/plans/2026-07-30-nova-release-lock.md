# Nova Release Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fail-closed, deterministic local release pipeline that snapshots approved Nova source from the dirty live workspace, verifies it in clean Git worktrees, and promotes only a passing candidate to local `master`.

**Architecture:** A pure snapshot-policy module classifies every repository path, a manifest module hashes the approved candidate deterministically, and a worktree module performs guarded Git/filesystem operations. A bounded controller composes those pieces with the existing release-security scanner and a subprocess-based verification runner; a separate explicit promotion command creates a rollback branch and a `--no-ff` merge without touching the live worktree.

**Tech Stack:** Python 3.11 standard library (`argparse`, `dataclasses`, `enum`, `fnmatch`, `hashlib`, `json`, `os`, `pathlib`, `shutil`, `subprocess`, `tempfile`, `time`, `urllib`), Git worktrees, existing `nova_release_security`, pytest, Node's built-in test runner.

## Global Constraints

- Do not modify, clean, reset, stage, or commit unrelated files in the live dirty worktree.
- Do not stop, restart, or reconfigure the running Nova server.
- Do not push branches, tags, or commits to a remote.
- Do not install new packages; use Python 3.11 standard library and existing project dependencies.
- Snapshot exclusions override inclusions, and unmatched paths are `ambiguous`.
- Never copy model weights, adapters, checkpoints, training data, private memory, databases, logs, generated media, remote attachments, secrets, or machine-local configuration.
- Reject symlinks and junctions whose resolved targets leave the repository.
- Reports live under Git's local administrative directory; temporary worktrees live beneath a verified Release Lock temporary root outside the repository.
- The committed content manifest excludes its own path from its file inventory and contains no timestamp or self-referential commit hash.
- Promotion is a separate explicit operation and always creates a merge commit.
- Never use `git reset --hard`, `git checkout --`, or an unchecked recursive delete.

## File Structure

### Create

- `config/nova_release_snapshot_policy.json` — versioned include/exclude/ambiguous and size policy.
- `src/nova_release_policy.py` — pure path classification and workspace scan.
- `src/nova_release_manifest.py` — canonical hashes, deterministic content manifest, and local run report.
- `src/nova_release_worktree.py` — guarded Git commands, worktree creation, overlay, cleanup, and promotion.
- `src/nova_release_gates.py` — bounded subprocess gates and result capture.
- `src/nova_release_lock.py` — preflight/build/promote orchestration and state transitions.
- `tools/nova_release_lock.py` — command-line entry point.
- `tools/nova_release_smoke.py` — isolated clean-start HTTP smoke process.
- `tests/test_nova_release_policy.py` — classification and filesystem-boundary tests.
- `tests/test_nova_release_manifest.py` — hash and canonical serialization tests.
- `tests/test_nova_release_worktree.py` — temporary Git repository/worktree tests.
- `tests/test_nova_release_gates.py` — timeout, output, environment, and smoke-runner tests.
- `tests/test_nova_release_lock.py` — controller and promotion integration tests.
- `docs/NOVA_RELEASE_LOCK.md` — operator guide, failure recovery, and rollback.

### Modify

- `src/nova_release_security.py:1-96` — avoid reading through unsafe links and report path escapes.
- `tests/test_nova_release_security.py:1-53` — cover link escape and new result field.
- `docs/NOVA_COGNITIVE_OPERATING_LAYER.md:280-310` — link Release Lock commands from existing release documentation.

---

### Task 1: Versioned Snapshot Policy and Workspace Classification

**Files:**
- Create: `config/nova_release_snapshot_policy.json`
- Create: `src/nova_release_policy.py`
- Create: `tests/test_nova_release_policy.py`

**Interfaces:**
- Produces: `SnapshotClass`, `SnapshotDecision`, `SnapshotReport`, `SnapshotPolicy.load(path)`, `SnapshotPolicy.classify(path, size_bytes, is_link)`, and `scan_workspace(repo_root, policy, tracked_paths, deleted_paths)`.
- Consumes: repository-relative POSIX paths and Git-tracked/deleted path sets supplied later by `nova_release_worktree`.

- [ ] **Step 1: Write failing policy precedence and ambiguity tests**

```python
from pathlib import Path

from nova_release_policy import SnapshotClass, SnapshotPolicy


def test_exclusion_overrides_inclusion(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        """{
          "schema_version": "1.0",
          "include": ["src/**", "config/*.example.json"],
          "exclude": ["**/*.db", "config/*.local.json"],
          "ambiguous": ["**/*.exe"],
          "allowed_binary_suffixes": [".png"],
          "max_static_asset_bytes": 5242880
        }""",
        encoding="utf-8",
    )
    policy = SnapshotPolicy.load(policy_path)

    assert policy.classify("src/nova.py", size_bytes=12).classification is SnapshotClass.INCLUDE
    assert policy.classify("src/private.db", size_bytes=12).classification is SnapshotClass.EXCLUDE
    assert policy.classify("config/workflow.local.json", size_bytes=12).classification is SnapshotClass.EXCLUDE
    assert policy.classify("tools/cloudflared.exe", size_bytes=12).classification is SnapshotClass.AMBIGUOUS
    assert policy.classify("mystery.xyz", size_bytes=12).classification is SnapshotClass.AMBIGUOUS
```

```python
def test_large_static_asset_and_link_fail_closed(tmp_path: Path) -> None:
    policy = SnapshotPolicy.load(Path("config/nova_release_snapshot_policy.json"))

    large = policy.classify("assets/hero.png", size_bytes=5_242_881)
    linked = policy.classify("assets/hero.png", size_bytes=10, is_link=True)

    assert large.classification is SnapshotClass.AMBIGUOUS
    assert large.rule == "static_asset_too_large"
    assert linked.classification is SnapshotClass.AMBIGUOUS
    assert linked.rule == "filesystem_link_requires_boundary_check"
```

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_policy.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'nova_release_policy'`.

- [ ] **Step 3: Add the versioned policy file**

Create `config/nova_release_snapshot_policy.json` with these exact categories:

```json
{
  "schema_version": "1.0",
  "include": [
    "src/**",
    "tests/**",
    "tools/**",
    "scripts/**",
    "docs/**",
    "assets/**",
    "autonomous_skills/**",
    "benchmark_lab/**",
    "codex_upgrade/**",
    "face_display/**",
    "mobile_bridge/**",
    "nova_mini_llm/**",
    "science_mastery/**",
    "voice_camera_runtime/**",
    "config/nova_release_snapshot_policy.json",
    "config/*.example.json",
    "config/*.example.yaml",
    "*.py",
    "*.html",
    "*.js",
    "*.mjs",
    "*.md",
    "*.txt",
    "*.bat",
    "*.sh",
    "CODEX_CLOUD_MANIFEST.json",
    "requirements-*.txt",
    "requirements-*.lock",
    "pytest.ini",
    ".gitignore",
    "NOVA_RELEASE_MANIFEST.json",
    "manifest.webmanifest",
    "service-worker.js"
  ],
  "exclude": [
    ".git",
    ".git/**",
    ".worktrees/**",
    ".codex-remote-attachments/**",
    ".pytest_cache/**",
    "__pycache__/**",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pyo",
    ".env",
    ".env.*",
    ".nova_llm_config",
    "nova_llm_config.json",
    "nova_remote_known_hosts*",
    "config/*.local.json",
    "data/**",
    "**/data/**",
    "logs/**",
    "**/logs/**",
    "reports/**",
    "**/reports/**",
    "exports/**",
    "**/exports/**",
    "backups/**",
    "**/backups/**",
    "checkpoints/**",
    "**/checkpoints/**",
    "adapters/**",
    "**/adapters/**",
    "models/**",
    "**/models/**",
    "training_data/**",
    "**/training_data/**",
    "nova_memory/**",
    "nova_training_logs/**",
    "tokenizer/**",
    "evidence/**",
    "sandbox/**",
    "quality_gate_screenshots/**",
    "benchmark_lab/exports/**",
    "benchmark_lab/route_traces/**",
    "nova_mini_llm/data.txt",
    "artifacts/**",
    "**/*.db",
    "**/*.db-wal",
    "**/*.db-shm",
    "**/*.log",
    "**/*.bak",
    "**/*.zip",
    "**/*.tar.gz",
    "**/*.pt",
    "**/*.pth",
    "**/*.gguf",
    "**/*.safetensors",
    "**/*.ckpt"
  ],
  "ambiguous": [
    "**/*.exe",
    "**/*.dll",
    "**/*.bin",
    "**/*.msi",
    "**/*.onnx"
  ],
  "allowed_binary_suffixes": [
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".woff",
    ".woff2"
  ],
  "max_static_asset_bytes": 5242880
}
```

- [ ] **Step 4: Implement the pure classifier and report types**

Use exact signatures and fail-closed precedence:

```python
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
```

`SnapshotPolicy.classify()` must normalize `\` to `/`, reject absolute paths and `..` segments, apply exclusions before ambiguous rules and inclusions, reject unapproved binary suffixes, enforce the static-asset size cap, and return `AMBIGUOUS` when no rule matches.

Directory matching must test both `path` and `path + "/"` so a rule such as `data/**` safely prunes the `data` directory itself. `scan_workspace()` must use `os.walk(..., followlinks=False)`, sort directories and files, prune only policy-excluded directories, record links and Windows reparse points without following them, add tracked deletion records, and return decisions sorted by normalized path. On Windows, detect reparse points from `lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT`.

- [ ] **Step 5: Add traversal, deterministic-order, deletion, and real-policy tests**

```python
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
```

- [ ] **Step 6: Run the focused tests**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_policy.py -q
```

Expected: all policy tests pass.

- [ ] **Step 7: Commit the policy unit**

```powershell
git add -- config/nova_release_snapshot_policy.json src/nova_release_policy.py tests/test_nova_release_policy.py
git commit -m "feat: add fail-closed release snapshot policy"
```

---

### Task 2: Harden Existing Release Security Against Filesystem Escapes

**Files:**
- Modify: `src/nova_release_security.py:1-96`
- Modify: `tests/test_nova_release_security.py:1-53`

**Interfaces:**
- Consumes: candidate root from `nova_release_lock`.
- Produces: existing `inspect_release()` behavior plus `path_escape_findings: list[str]` on `ReleaseSecurityResult`.

- [ ] **Step 1: Write a failing unsafe-link test**

```python
import os
import pytest


def test_release_rejects_link_that_resolves_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("private", encoding="utf-8")
    link = tmp_path / "outside-link.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem links are unavailable for this user")

    result = inspect_release(tmp_path)

    assert not result.passed
    assert result.path_escape_findings == ["outside-link.txt"]
```

- [ ] **Step 2: Verify the new test fails**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_security.py::test_release_rejects_link_that_resolves_outside_root -q
```

Expected: failure because `ReleaseSecurityResult` has no `path_escape_findings`.

- [ ] **Step 3: Implement non-following enumeration and escape reporting**

Add:

```python
@dataclass
class ReleaseSecurityResult:
    passed: bool
    inspected_files: int
    unexpected_files: list[str] = field(default_factory=list)
    secret_findings: list[str] = field(default_factory=list)
    oversized_debug_artifacts: list[str] = field(default_factory=list)
    path_escape_findings: list[str] = field(default_factory=list)
    version: str = RELEASE_SECURITY_VERSION
```

Replace `Path.rglob()` with sorted `os.walk(base, followlinks=False)`. Treat `Path.is_symlink()` and a Windows `FILE_ATTRIBUTE_REPARSE_POINT` from `lstat()` as links. For each linked directory or file, resolve it with `strict=False`; append its relative POSIX path when the result is outside `base` or when resolution raises `OSError`. Never open linked file content. Include `path_escape_findings` in the `passed` calculation.

- [ ] **Step 4: Run the existing and new security tests**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_security.py -q
```

Expected: all tests pass, including the existing secret, lockfile, and SBOM tests.

- [ ] **Step 5: Commit the security hardening**

```powershell
git add -- src/nova_release_security.py tests/test_nova_release_security.py
git commit -m "fix: reject release filesystem escapes"
```

---

### Task 3: Deterministic Content Manifest and Local Run Reports

**Files:**
- Create: `src/nova_release_manifest.py`
- Create: `tests/test_nova_release_manifest.py`

**Interfaces:**
- Produces: `FileDigest`, `GateSummary`, `ReleaseManifest`, `RunReport`, `sha256_file()`, `build_content_manifest()`, `canonical_json()`, `write_json_atomic()`, and `release_state_root()`.
- Consumes: `SnapshotReport`, source revision, candidate branch, summarized gate outcomes, and Git common-directory path.

- [ ] **Step 1: Write failing determinism and self-exclusion tests**

```python
from pathlib import Path

from nova_release_manifest import build_content_manifest, canonical_json


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
```

- [ ] **Step 2: Verify the missing module failure**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_manifest.py -q
```

Expected: collection fails with `ModuleNotFoundError`.

- [ ] **Step 3: Implement canonical manifest types**

Use:

```python
MANIFEST_SCHEMA_VERSION = "1.0"
MANIFEST_NAME = "NOVA_RELEASE_MANIFEST.json"


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
```

`canonical_json()` must use `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"`.

`build_content_manifest()` must enumerate regular non-link files in sorted POSIX order, skip `.git`, `.git/**`, and `NOVA_RELEASE_MANIFEST.json`, hash in 1 MiB blocks, sort maps/lists, and derive `release_id` from the source commit plus a SHA-256 digest of the canonical content fields.

- [ ] **Step 4: Add atomic run-report storage**

```python
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
```

`release_state_root(git_common_dir)` returns `<git-common-dir>/nova-release-lock`. `write_json_atomic()` writes to a sibling `.tmp`, flushes and calls `os.fsync()`, then replaces the destination with `os.replace()`.

- [ ] **Step 5: Add hash-change, atomic-write, and run-report tests**

```python
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
```

Assert the state root is under the supplied Git common directory and never appears in the candidate file inventory.

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_manifest.py -q
```

Expected: all manifest tests pass.

Commit:

```powershell
git add -- src/nova_release_manifest.py tests/test_nova_release_manifest.py
git commit -m "feat: add deterministic release manifests"
```

---

### Task 4: Guarded Git Worktrees and Snapshot Overlay

**Files:**
- Create: `src/nova_release_worktree.py`
- Create: `tests/test_nova_release_worktree.py`

**Interfaces:**
- Produces: `GitError`, `GitRepository`, `git_output()`, `list_tracked_paths()`, `list_deleted_paths()`, `create_candidate_worktree()`, `apply_snapshot()`, `commit_candidate()`, and `cleanup_worktree()`.
- Consumes: `SnapshotReport` from Task 1 and candidate/source paths.

- [ ] **Step 1: Write failing temporary-repository and overlay tests**

```python
import subprocess


def run_test_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def init_repo(root: Path) -> GitRepository:
    root.mkdir(parents=True)
    run_test_git(root, "init", "-b", "master")
    run_test_git(root, "config", "user.name", "Nova Release Test")
    run_test_git(root, "config", "user.email", "nova-release@example.invalid")
    (root / "src").mkdir()
    (root / "src" / "nova.py").write_text("committed\n", encoding="utf-8")
    run_test_git(root, "add", "src/nova.py")
    run_test_git(root, "commit", "-m", "initial")
    return GitRepository.discover(root)


def report_for(root: Path, include: list[str]) -> SnapshotReport:
    decisions = [
        SnapshotDecision(
            path=path,
            classification=SnapshotClass.INCLUDE,
            rule="test_include",
            tracked=run_test_git(root, "ls-files", "--", path) == path,
        )
        for path in include
    ]
    return SnapshotReport(schema_version="1.0", decisions=decisions)


def test_candidate_overlay_preserves_source_worktree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    source = repo.root
    (source / "src" / "nova.py").write_text("working copy\n", encoding="utf-8")
    (source / "src" / "new.py").write_text("new\n", encoding="utf-8")
    report = report_for(source, include=["src/nova.py", "src/new.py"])
    candidate = tmp_path / "release-temp" / "candidate"

    create_candidate_worktree(
        repo,
        source_ref="HEAD",
        branch_name="codex/release-lock-test",
        destination=candidate,
    )
    apply_snapshot(source, candidate, report, tmp_path / "release-temp")

    assert (candidate / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"
    assert (candidate / "src" / "new.py").read_text(encoding="utf-8") == "new\n"
    assert (source / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"
    assert git_output(repo.root, "status", "--short") != ""
```

- [ ] **Step 2: Verify the missing module failure**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_worktree.py -q
```

Expected: collection fails with `ModuleNotFoundError`.

- [ ] **Step 3: Implement Git command and path guards**

```python
@dataclass(frozen=True)
class GitRepository:
    root: Path
    common_dir: Path

    @classmethod
    def discover(cls, root: str | Path) -> "GitRepository":
        resolved = Path(root).resolve()
        top = Path(git_output(resolved, "rev-parse", "--show-toplevel")).resolve()
        common = Path(git_output(top, "rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = (top / common).resolve()
        return cls(root=top, common_dir=common)
```

All Git calls use `subprocess.run(["git", "-C", str(root), *args], shell=False, capture_output=True, text=True, timeout=60)`. `git_output()` raises `GitError` with redacted, bounded stderr.

Add `_safe_destination(path, approved_temp_root)` that requires the resolved destination to be a strict descendant of the resolved temporary root and rejects the repository root, drive root, home directory, and empty path.

- [ ] **Step 4: Implement worktree creation and overlay**

`create_candidate_worktree()` runs:

```text
git branch <branch_name> <source_ref>
git worktree add <destination> <branch_name>
```

It first rejects an existing branch or destination.

`apply_snapshot()` must:

1. Reject a report containing any ambiguous decision.
2. Validate both roots and every normalized relative path.
3. Copy included present regular files with `shutil.copy2`.
4. Remove included tracked deletions from the candidate.
5. Remove excluded tracked files from the candidate.
6. Reject all source links.
7. Use a guarded removal helper that verifies the candidate target before deleting; directories may be recursively removed only inside the verified candidate root.

- [ ] **Step 5: Add escape, ambiguity, deletion, and cleanup tests**

```python
def test_apply_snapshot_rejects_escape_and_ambiguity(tmp_path: Path) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "temp" / "candidate"
    source.mkdir()
    candidate.mkdir(parents=True)

    escape = SnapshotReport(
        schema_version="1.0",
        decisions=[
            SnapshotDecision("../private.txt", SnapshotClass.INCLUDE, "invalid_test_path")
        ],
    )
    with pytest.raises(ReleasePathError):
        apply_snapshot(source, candidate, escape, tmp_path / "temp")

    report = SnapshotReport(
        schema_version="1.0",
        decisions=[SnapshotDecision("mystery.bin", SnapshotClass.AMBIGUOUS, "binary")],
    )
    with pytest.raises(AmbiguousSnapshotError):
        apply_snapshot(source, candidate, report, tmp_path / "temp")
```

Test `cleanup_worktree()` against a destination outside the approved temporary root and assert it refuses without removing anything.

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_worktree.py -q
```

Expected: all worktree tests pass.

Commit:

```powershell
git add -- src/nova_release_worktree.py tests/test_nova_release_worktree.py
git commit -m "feat: isolate release candidates in guarded worktrees"
```

---

### Task 5: Bounded Verification Gates and Clean-Start Smoke Test

**Files:**
- Create: `src/nova_release_gates.py`
- Create: `tools/nova_release_smoke.py`
- Create: `tests/test_nova_release_gates.py`

**Interfaces:**
- Produces: `GateDefinition`, `GateResult`, `redact_gate_output()`, `GateRunner.run()`, `default_gate_definitions()`, and `run_clean_start_smoke()`.
- Consumes: candidate root, run-report directory, Python executable, and a sanitized environment.

- [ ] **Step 1: Write failing gate success, timeout, and output-bound tests**

```python
def test_gate_runner_records_observed_result(tmp_path: Path) -> None:
    gate = GateDefinition(
        name="probe",
        argv=(sys.executable, "-c", "print('passed')"),
        timeout_seconds=5,
    )
    result = GateRunner(tmp_path, tmp_path / "reports").run(gate)
    assert result.passed is True
    assert result.exit_code == 0
    assert result.command == [sys.executable, "-c", "print('passed')"]
    assert result.stdout_tail == "passed"


def test_gate_runner_times_out_and_kills_process_tree(tmp_path: Path) -> None:
    gate = GateDefinition(
        name="timeout",
        argv=(sys.executable, "-c", "import time; time.sleep(30)"),
        timeout_seconds=1,
    )
    result = GateRunner(tmp_path, tmp_path / "reports").run(gate)
    assert result.passed is False
    assert result.timed_out is True


def test_gate_runner_redacts_secret_output(tmp_path: Path) -> None:
    gate = GateDefinition(
        name="redaction",
        argv=(
            sys.executable,
            "-c",
            "print('Authorization: Bearer secret-token-value-1234567890')",
        ),
        timeout_seconds=5,
    )
    result = GateRunner(tmp_path, tmp_path / "reports").run(gate)
    assert "secret-token" not in result.stdout_tail
    assert "[REDACTED]" in result.stdout_tail
```

- [ ] **Step 2: Verify the missing module failure**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_gates.py -q
```

Expected: collection fails with `ModuleNotFoundError`.

- [ ] **Step 3: Implement bounded gate execution**

```python
@dataclass(frozen=True)
class GateDefinition:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: int
    required: bool = True


@dataclass
class GateResult:
    name: str
    command: list[str]
    passed: bool
    exit_code: int | None
    duration_seconds: float
    timed_out: bool
    stdout_tail: str
    stderr_tail: str
```

Use these exact public signatures:

```text
GateRunner(
    candidate_root: str | Path,
    report_dir: str | Path,
    *,
    base_environment: Mapping[str, str] | None = None,
    max_output_bytes: int = 65_536,
)
GateRunner.run(gate: GateDefinition) -> GateResult
default_gate_definitions(
    candidate_root: str | Path,
    run_report_dir: str | Path,
    *,
    python_executable: str = sys.executable,
) -> list[GateDefinition]
run_clean_start_smoke(
    candidate_root: str | Path,
    report_path: str | Path,
    *,
    timeout_seconds: int = 60,
) -> GateResult
```

`GateRunner.run()` must use `shell=False`, a sanitized environment, a candidate-root working directory, a configurable 64 KiB tail per stream, and process-tree termination. On Windows create a new process group and use `taskkill /PID <pid> /T /F` only for the exact child PID; on POSIX start a new session and kill that process group.

Before persisting stdout or stderr, `redact_gate_output()` must replace matches from `nova_release_security.SECRET_PATTERNS`, `Authorization:` header values, and `Bearer` tokens with `[REDACTED]`. It must not store complete prompts, responses, memory contents, or database rows.

Build the child environment from this non-secret operating-system allowlist: `PATH`, `SYSTEMROOT`, `WINDIR`, `TEMP`, `TMP`, `PATHEXT`, `COMSPEC`, `HOME`, `USERPROFILE`, `LOCALAPPDATA`, and `APPDATA`. Do not copy authorization, token, password, key, or secret-named environment variables. Explicitly set:

```python
{
    "PYTHONPATH": str(candidate_root / "src"),
    "NOVA_MODEL_WARMUP": "false",
    "NOVA_REVIEWER_WARMUP": "false",
    "NOVA_ENABLE_REMOTE_ACCESS": "false",
    "NOVA_ALLOW_REMOTE_MODELS": "false",
    "NOVA_COMPANION_ENABLED": "true",
    "NOVA_COMPANION_DEFAULT": "false",
}
```

- [ ] **Step 4: Define the required gates**

`default_gate_definitions()` returns these exact logical gates:

1. `release_focused`: pytest for all six Release Lock/security test modules.
2. `dependency_lock`: `python -m nova_release_security verify-lock requirements-runtime.lock`.
3. `sbom`: `python -m nova_release_security sbom <run-report>/nova-sbom.json`.
4. `javascript`: pytest `tests/test_nova_companion_javascript.py -q`.
5. `application_acceptance`: pytest for practical support, Companion routes/source/PWA, model provider, memory V2, and Companion vision.
6. `python_full`: `python -m pytest -q`.
7. `conversation_560`: `tools/run_conversation_eval.py` with the checked-in 560-case pack and an output path beneath the run-report directory.
8. `clean_start_smoke`: `tools/nova_release_smoke.py --root <candidate> --report <run-report>/smoke.json`.

Resolve `py -3.11` to `sys.executable` inside tests and use `sys.executable` for released commands so the candidate is verified in the active Python 3.11 environment.

- [ ] **Step 5: Implement the clean-start smoke helper**

`run_clean_start_smoke()` must choose an unused loopback port, launch `nova_enhanced_server.py <port>` from the candidate, wait up to 60 seconds for `/healthz`, execute `tools/nova_smoke_check.py --url <base-url>`, record server stdout/stderr outside the candidate, and terminate the exact process tree in `finally`.

The subprocess environment must disable model warm-up and remote access. The smoke test is read-only; chat/follow-up, routing, memory, vision, and mobile behavior are covered by the deterministic application-acceptance gate.

- [ ] **Step 6: Add a fake-server smoke lifecycle test**

Create a temporary Python HTTP server fixture that serves healthy `/healthz`, then assert the helper reports startup, probe, and cleanup. Add a failure fixture that exits before health and assert the result is failed rather than reported as successful.

- [ ] **Step 7: Run focused tests and commit**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_gates.py -q
```

Expected: all gate tests pass and no child process remains.

Commit:

```powershell
git add -- src/nova_release_gates.py tools/nova_release_smoke.py tests/test_nova_release_gates.py
git commit -m "feat: add bounded release verification gates"
```

---

### Task 6: Preflight and Candidate-Build Controller

**Files:**
- Create: `src/nova_release_lock.py`
- Create: `tests/test_nova_release_lock.py`

**Interfaces:**
- Produces: `ReleaseStatus`, `ReleasePaths`, `ReleaseRun`, `NovaReleaseLock.preflight()`, `NovaReleaseLock.load_run()`, `NovaReleaseLock.build()`, and persisted `RunReport`.
- Consumes: all Tasks 1–5 interfaces plus existing `inspect_release()`.

- [ ] **Step 1: Write a failing preflight fail-closed test**

```python
import subprocess
import sys
import shutil
import os
from pathlib import Path

from nova_release_gates import GateDefinition


def test_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def make_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    test_git(root, "init", "-b", "master")
    test_git(root, "config", "user.name", "Nova Release Test")
    test_git(root, "config", "user.email", "nova-release@example.invalid")
    (root / "src").mkdir()
    (root / "src" / "nova.py").write_text("committed\n", encoding="utf-8")
    (root / "config").mkdir()
    shutil.copy2(
        Path("config/nova_release_snapshot_policy.json"),
        root / "config" / "nova_release_snapshot_policy.json",
    )
    test_git(root, "add", ".")
    test_git(root, "commit", "-m", "initial")
    test_git(root, "switch", "-c", "codex/test-release-source")
    (root / "src" / "nova.py").write_text("working copy\n", encoding="utf-8")
    return root


def git_head(root: Path, ref: str) -> str:
    return test_git(root, "rev-parse", ref)


def failing_gate() -> GateDefinition:
    return GateDefinition(
        name="forced_failure",
        argv=(sys.executable, "-c", "raise SystemExit(9)"),
        timeout_seconds=5,
    )


def passing_gate() -> GateDefinition:
    return GateDefinition(
        name="forced_success",
        argv=(sys.executable, "-c", "print('verified')"),
        timeout_seconds=5,
    )


def test_preflight_writes_report_and_blocks_ambiguous_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    (repo / "mystery.exe").write_bytes(b"MZ")
    lock = NovaReleaseLock(repo_root=repo, temp_root=tmp_path / "release-temp")

    result = lock.preflight()

    assert result.status is ReleaseStatus.FAILED
    assert result.failure_gate == "snapshot_policy"
    assert result.snapshot_report.ambiguous[0].path == "mystery.exe"
    assert result.report_path.is_file()
    assert git_head(repo, "master") == result.master_before
```

- [ ] **Step 2: Verify the missing module failure**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_lock.py::test_preflight_writes_report_and_blocks_ambiguous_file -q
```

Expected: collection fails with `ModuleNotFoundError`.

- [ ] **Step 3: Implement state and path types**

```python
class ReleaseStatus(str, Enum):
    PLANNED = "PLANNED"
    BUILDING = "BUILDING"
    VERIFIED = "VERIFIED"
    PROMOTED = "PROMOTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ReleasePaths:
    run_dir: Path
    candidate_worktree: Path
    master_worktree: Path
    preflight_report: Path
    gate_report: Path
    run_report: Path


@dataclass
class ReleaseRun:
    run_id: str
    status: ReleaseStatus
    source_branch: str
    source_commit: str
    master_before: str
    paths: ReleasePaths
    snapshot_report: SnapshotReport
    candidate_branch: str | None = None
    candidate_commit: str | None = None
    master_after: str | None = None
    rollback_ref: str | None = None
    failure_gate: str | None = None
    report_path: Path | None = None
```

Generate `run_id` as UTC `YYYYMMDDTHHMMSSZ-<source-short-sha>-<four-random-hex>` using `secrets.token_hex(2)`. Store reports under `<git-common-dir>/nova-release-lock/runs/<run-id>`. Store temporary worktrees under `<configured-temp-root>/<repository-hash>/<run-id>`.

`preflight() -> ReleaseRun` creates and persists a new run. `load_run(run_id: str) -> ReleaseRun` reconstructs only from the local run report and referenced preflight report after validating the run ID with `re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{7,12}-[0-9a-f]{4}", run_id)`. `build(run: ReleaseRun | str) -> ReleaseRun` accepts either the just-created object or a validated persisted run ID.

- [ ] **Step 4: Implement `preflight()`**

`preflight()` must:

1. Discover the Git repository/common directory.
2. Read source branch, source commit, and local `master` commit.
3. Load the versioned policy.
4. Read tracked and deleted paths from Git.
5. Scan the entire source worktree without following links.
6. Write include/exclude/deletion/ambiguous decisions atomically.
7. Record the exact source and master revisions in `RunReport`.
8. Return `FAILED` on ambiguity without creating a branch or worktree.

- [ ] **Step 5: Write failing build-order and no-master-change tests**

```python
def test_build_stops_before_commit_when_gate_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    master_before = git_head(repo, "master")
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[failing_gate()],
    )

    result = lock.build(lock.preflight())

    assert result.status is ReleaseStatus.FAILED
    assert result.failure_gate == "forced_failure"
    assert result.candidate_commit is None
    assert git_head(repo, "master") == master_before
    assert (repo / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"
```

- [ ] **Step 6: Implement `build()` as a bounded state transition**

`build()` accepts only a passing `PLANNED` result. It must:

1. Re-check source `HEAD` and `master` against preflight.
2. Create the timestamped candidate branch/worktree.
3. Apply the approved snapshot.
4. Run `inspect_release(candidate_root)` and policy-scan the candidate.
5. Run required gates sequentially, stopping on the first failure.
6. Remove only newly generated policy-excluded artifacts inside the verified candidate root.
7. Fail if a gate generated an included or ambiguous untracked file.
8. Build and atomically write `NOVA_RELEASE_MANIFEST.json`.
9. Rebuild the manifest and compare canonical bytes.
10. Stage candidate contents and commit with `release: lock Nova snapshot <release-id>`.
11. Require a clean candidate worktree.
12. Record the candidate commit and set status `VERIFIED`.

Every exception updates the run report to `FAILED` with a safe category before propagating a nonzero CLI result.

- [ ] **Step 7: Add security-failure, manifest-repeatability, and source-unchanged tests**

Add tests that inject a secret into an otherwise included file, cause a gate to create an unexpected file, and change source `HEAD` after preflight. Each test must assert candidate promotion does not occur and `master` remains at the original commit.

- [ ] **Step 8: Run controller tests and commit**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_lock.py -q -k "preflight or build"
```

Expected: all preflight/build tests pass.

Commit:

```powershell
git add -- src/nova_release_lock.py tests/test_nova_release_lock.py
git commit -m "feat: build verified Nova release candidates"
```

---

### Task 7: Explicit Promotion, Rollback Reference, and Conflict Safety

**Files:**
- Modify: `src/nova_release_worktree.py`
- Modify: `src/nova_release_lock.py`
- Modify: `tests/test_nova_release_worktree.py`
- Modify: `tests/test_nova_release_lock.py`

**Interfaces:**
- Produces: worktree-local `GitPromotionResult`, controller-level `PromotionResult`, and `NovaReleaseLock.promote(run_id)`.
- Consumes: a persisted run with status `VERIFIED`, candidate commit, and preflight `master_before`.

- [ ] **Step 1: Write failing successful-promotion test**

```python
from types import SimpleNamespace


def make_verified_release(tmp_path: Path) -> tuple[Path, SimpleNamespace]:
    repo = make_repo(tmp_path / "repo")
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[passing_gate()],
    )
    planned = lock.preflight()
    verified = lock.build(planned)
    assert verified.status is ReleaseStatus.VERIFIED
    return repo, SimpleNamespace(lock=lock, run_id=verified.run_id)


def test_promote_creates_rollback_ref_and_merge_commit(tmp_path: Path) -> None:
    repo, verified = make_verified_release(tmp_path)
    lock = verified.lock

    result = lock.promote(verified.run_id)

    assert result.status is ReleaseStatus.PROMOTED
    assert git_head(repo, "master") == result.master_after
    assert git_output(repo, "rev-parse", result.rollback_ref) == result.master_before
    parents = git_output(repo, "show", "-s", "--format=%P", result.master_after).split()
    assert parents == [result.master_before, result.candidate_commit]
    assert result.rollback_command == [
        "git",
        "-C",
        str(repo),
        "revert",
        "-m",
        "1",
        result.master_after,
    ]
```

- [ ] **Step 2: Verify the promotion test fails**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_lock.py::test_promote_creates_rollback_ref_and_merge_commit -q
```

Expected: failure because `promote()` is not implemented.

- [ ] **Step 3: Implement guarded promotion**

Add `GitPromotionResult` to `nova_release_worktree.py` without importing controller types:

```python
@dataclass(frozen=True)
class GitPromotionResult:
    master_before: str
    master_after: str
    candidate_commit: str
    rollback_ref: str
```

Add the user-facing result to `nova_release_lock.py`:

```python
@dataclass(frozen=True)
class PromotionResult:
    status: ReleaseStatus
    master_before: str
    master_after: str
    candidate_commit: str
    rollback_ref: str
    rollback_command: list[str]
```

`promote()` must:

1. Load the run report and require `VERIFIED`.
2. Verify the candidate commit exists and matches the report.
3. Verify `refs/heads/master` still equals `master_before`.
4. Refuse when `master` is checked out in another worktree.
5. Create `refs/heads/codex/rollback-release-lock-<run-id>` at `master_before`.
6. Add the separate clean master worktree.
7. Run `git merge --no-ff --no-edit <candidate-commit>`.
8. On conflict, run `git merge --abort`, verify master is unchanged, set `FAILED`, and preserve diagnostics.
9. Verify the resulting merge parents are exactly `master_before` and `candidate_commit`.
10. Persist `master_after`, rollback ref, and the non-destructive `git revert -m 1` command.

- [ ] **Step 4: Add moved-master, conflict, and duplicate-promotion tests**

Each failure test must assert:

- `master` is not silently overwritten.
- The rollback ref never points to a different commit.
- A second call after `PROMOTED` is rejected as an invalid state transition.
- No destructive reset command appears in captured Git calls.

- [ ] **Step 5: Run promotion tests and commit**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_worktree.py tests/test_nova_release_lock.py -q
```

Expected: all worktree, build, conflict, promotion, and rollback tests pass.

Commit:

```powershell
git add -- src/nova_release_worktree.py src/nova_release_lock.py tests/test_nova_release_worktree.py tests/test_nova_release_lock.py
git commit -m "feat: promote releases with deterministic rollback"
```

---

### Task 8: CLI, Operator Documentation, and End-to-End Verification

**Files:**
- Create: `tools/nova_release_lock.py`
- Create: `docs/NOVA_RELEASE_LOCK.md`
- Modify: `docs/NOVA_COGNITIVE_OPERATING_LAYER.md:280-310`
- Modify: `tests/test_nova_release_lock.py`

**Interfaces:**
- Produces CLI commands `plan`, `build`, `promote`, `status`, and `cleanup`.
- Consumes `NovaReleaseLock` and persisted run reports.

- [ ] **Step 1: Write failing CLI default-safety and JSON-output tests**

```python
def run_cli(repo: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "tools" / "nova_release_lock.py"),
            "--repo",
            str(repo),
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
    )


def test_cli_defaults_to_plan_and_never_promotes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    completed = run_cli(repo, [])
    payload = json.loads(completed.stdout)
    assert completed.returncode in {0, 2}
    assert payload["operation"] == "plan"
    assert payload["promoted"] is False
    assert git_head(repo, "master") == payload["master_before"]


def test_cli_promote_requires_explicit_run_id(tmp_path: Path) -> None:
    completed = run_cli(tmp_path, ["promote"])
    assert completed.returncode == 2
    assert "--run-id" in completed.stderr
```

- [ ] **Step 2: Verify the missing CLI failure**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_lock.py -q -k "cli"
```

Expected: CLI tests fail because `tools/nova_release_lock.py` does not exist.

- [ ] **Step 3: Implement the CLI**

Use these commands:

```text
py -3.11 tools/nova_release_lock.py plan
py -3.11 tools/nova_release_lock.py build --run-id <planned-run-id>
py -3.11 tools/nova_release_lock.py status --run-id <run-id>
py -3.11 tools/nova_release_lock.py promote --run-id <verified-run-id>
py -3.11 tools/nova_release_lock.py cleanup --run-id <run-id>
```

With no subcommand, execute `plan`. `plan` and `status` are read-only except for local report files under Git administrative data. `build` may create only the candidate branch/worktree. `promote` is the only command allowed to change local `master`. `cleanup` validates the recorded worktree path against the configured temporary root before removing it and never deletes a branch, report, or rollback ref.

Return one JSON object to stdout with `operation`, `run_id`, `status`, `master_before`, `candidate_branch`, `candidate_commit`, `promoted`, `report_path`, and `failure_gate`. Return `0` for successful requested operation, `1` for an observed gate/build failure, and `2` for invalid input or unsafe state.

Expose `main(argv: Sequence[str] | None = None, *, controller_factory: Callable[..., NovaReleaseLock] = NovaReleaseLock) -> int` so CLI argument/serialization tests can inject a controller configured with deterministic gates without adding a production bypass flag or environment variable.

- [ ] **Step 4: Write the operator guide**

Document:

- The approved snapshot boundary.
- Why the live dirty workspace remains untouched.
- `plan → inspect report → build → status → promote`.
- How ambiguous files stop the run.
- Where run reports and temporary worktrees live.
- No-push/no-restart guarantees.
- Failure recovery.
- The exact rollback form:

```powershell
git -C "C:\path\to\NOVA LLM CREATURE DESKTOP" revert -m 1 <merge-commit>
```

- Cleanup semantics.
- How to inspect the candidate before promotion.
- A warning that `promote` changes only local `master`.

Add a short Release Lock link and command block to `docs/NOVA_COGNITIVE_OPERATING_LAYER.md`.

- [ ] **Step 5: Run all Release Lock tests**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest `
  tests/test_nova_release_policy.py `
  tests/test_nova_release_security.py `
  tests/test_nova_release_manifest.py `
  tests/test_nova_release_worktree.py `
  tests/test_nova_release_gates.py `
  tests/test_nova_release_lock.py -q
```

Expected: all Release Lock tests pass.

- [ ] **Step 6: Run the CLI against a disposable integration repository**

The integration test creates a temporary Git repository with a dirty included source file, an excluded database, and an untracked included test. It must:

1. Run `plan` and inspect classifications.
2. Run `build` with deterministic stub gates.
3. Assert the candidate contains source/test changes but no database.
4. Run `promote`.
5. Assert the live dirty source remains dirty and unchanged.
6. Assert local `master` is a merge commit.
7. Assert the rollback ref points to the prior `master`.

Implement the test with the injected controller factory:

```python
def test_cli_end_to_end_in_disposable_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_repo(tmp_path / "repo")
    (repo / "data").mkdir()
    (repo / "data" / "private.db").write_bytes(b"private")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_new.py").write_text(
        "def test_new():\n    assert True\n",
        encoding="utf-8",
    )
    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        gate_definitions=[passing_gate()],
    )

    assert cli_main(["--repo", str(repo), "plan"], controller_factory=lambda **_: lock) == 0
    planned = json.loads(capsys.readouterr().out)
    assert cli_main(
        ["--repo", str(repo), "build", "--run-id", planned["run_id"]],
        controller_factory=lambda **_: lock,
    ) == 0
    built = json.loads(capsys.readouterr().out)
    candidate = lock.load_run(built["run_id"]).paths.candidate_worktree
    assert (candidate / "tests" / "test_new.py").is_file()
    assert not (candidate / "data" / "private.db").exists()

    assert cli_main(
        ["--repo", str(repo), "promote", "--run-id", built["run_id"]],
        controller_factory=lambda **_: lock,
    ) == 0
    promoted = json.loads(capsys.readouterr().out)
    assert promoted["promoted"] is True
    assert git_head(repo, promoted["rollback_ref"]) == promoted["master_before"]
    assert len(test_git(repo, "show", "-s", "--format=%P", "master").split()) == 2
    assert (repo / "src" / "nova.py").read_text(encoding="utf-8") == "working copy\n"
```

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest tests/test_nova_release_lock.py::test_cli_end_to_end_in_disposable_repository -q
```

Expected: PASS.

- [ ] **Step 7: Run Nova's complete verification set**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest -q
```

Expected: complete Python suite passes with only the repository's established skips.

Run:

```powershell
py -3.11 -m pytest tests/test_nova_companion_javascript.py -q
```

Expected: Node-backed JavaScript suite passes.

Run:

```powershell
py -3.11 tools/run_conversation_eval.py `
  --pack data/evals/nova_conversation_variations_v1.json `
  --output "$env:TEMP\nova_release_lock_conversation_eval.json"
```

Expected: 560 of 560 deterministic conversation cases pass and no training record is written.

- [ ] **Step 8: Run a read-only preflight on the real Nova workspace**

Run:

```powershell
py -3.11 tools/nova_release_lock.py plan
```

Expected: JSON reports either `PLANNED` or fail-closed `FAILED` with exact ambiguous paths. Confirm `git status --short` shows no Release Lock changes outside the files intentionally implemented by this plan, and confirm the running Nova URL remains healthy.

- [ ] **Step 9: Commit CLI and documentation**

```powershell
git add -- tools/nova_release_lock.py docs/NOVA_RELEASE_LOCK.md docs/NOVA_COGNITIVE_OPERATING_LAYER.md tests/test_nova_release_lock.py
git commit -m "docs: add Nova Release Lock workflow"
```

## Completion Checklist

- [ ] Exclusion precedence and unmatched ambiguity are proven by tests.
- [ ] Symlink and junction escapes are not followed or read.
- [ ] Content hashes and canonical manifests are reproducible.
- [ ] The manifest does not hash itself or contain its own commit ID.
- [ ] Gate output is bounded, secrets are not inherited, and timed-out process trees are terminated.
- [ ] Candidate construction does not change the live worktree or local `master`.
- [ ] Any failed gate prevents a candidate commit and promotion.
- [ ] Promotion checks the original `master`, creates a rollback branch, and uses `--no-ff`.
- [ ] The rollback command is non-destructive and recorded.
- [ ] No command pushes, restarts Nova, downloads models, or installs packages.
- [ ] Full Python, JavaScript, 560-case conversation, and clean-start smoke gates pass.
