# Nova Sandboxed Release Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Nova release gates inside Windows Sandbox on Windows, reject malformed guest output, and close the run-report TOCTOU hole without changing promotion semantics.

**Architecture:** Keep `NovaReleaseLock` as the host authority, but move gate execution behind a sandbox provider boundary. The host assembles an approved input bundle, launches a disposable Windows Sandbox guest with a generated `.wsb`, and validates one bounded result file before promotion. Run-report reads become handle-pinned so a swapped path cannot be used after validation.

**Tech Stack:** Python standard library, existing release-lock modules, Windows Sandbox `.wsb` files, pytest, current Git worktree promotion flow.

**Spec:** `docs/superpowers/specs/2026-08-30-nova-sandboxed-release-lock-design.md`

## Global Constraints

- Windows: use Windows Sandbox when available; otherwise fail closed.
- Linux and macOS: fail closed for this release path.
- Windows Sandbox is the primary verification boundary on Windows.
- The host never trusts sandbox output as a source of truth until it has passed validation.
- Any uncertain state should stop the release rather than downgrade the boundary.

---

## File Map

- `src/nova_release_sandbox.py` owns the sandbox run-spec, `.wsb` generation, guest-plan serialization, result schema, and result validation helpers.
- `tools/nova_release_sandbox_guest.py` is the guest bootstrap entry point that runs inside the sandbox and writes one bounded result file.
- `src/nova_release_lock.py` remains the host release controller and switches verification to the sandbox provider.
- `src/nova_release_manifest.py` gains a handle-safe JSON read helper for persisted run state.
- `tests/test_nova_release_sandbox.py` covers the sandbox boundary and result validation in isolation.
- `tests/test_nova_release_lock.py` covers controller integration, promotion, and fail-closed behavior.
- `tests/test_nova_release_manifest.py` covers handle-pinned run-report reads and path-swap rejection.
- `docs/NOVA_RELEASE_LOCK.md` explains the operator-facing sandboxed release path.

## Task 1: Define the sandbox run contract and validation helpers

**Files:**
- Create: `src/nova_release_sandbox.py`
- Create: `tests/test_nova_release_sandbox.py`

**Interfaces:**
- Consumes: `nova_release_gates.GateDefinition`, approved candidate path, run id, nonce, and source commit.
- Produces: `SandboxRunSpec`, `SandboxGateResult`, `SandboxRunResult`, `SandboxProvider`, `WindowsSandboxProvider`, `build_windows_sandbox_config()`, `build_guest_plan()`, `validate_sandbox_result()`, and `load_sandbox_result()`.

- [ ] **Step 1: Write the failing boundary tests**

```python
def test_windows_sandbox_config_disables_network_clipboard_and_printers():
    spec = SandboxRunSpec(
        run_id="20260830T120000Z-abc123-00",
        nonce="nonce-1",
        source_commit="abc1234def5678",
        candidate_dir=Path("candidate"),
        output_dir=Path("output"),
        gates=(),
    )
    config = build_windows_sandbox_config(spec)
    assert "<Networking>Disable</Networking>" in config
    assert "<ClipboardRedirection>Disable</ClipboardRedirection>" in config
    assert "<PrinterRedirection>Disable</PrinterRedirection>" in config
```

- [ ] **Step 2: Run the tests to confirm the helpers do not exist yet**

Run: `py -3.11 -m pytest tests/test_nova_release_sandbox.py -q`

Expected: fail because the sandbox contract and validation helpers are not implemented yet.

- [ ] **Step 3: Implement the minimal contract and validation layer**

```python
@dataclass(frozen=True)
class SandboxRunSpec:
    run_id: str
    nonce: str
    source_commit: str
    candidate_dir: Path
    output_dir: Path
    gates: tuple[GateDefinition, ...]

def validate_sandbox_result(payload: Mapping[str, Any], *, expected: SandboxRunSpec) -> SandboxRunResult:
    if payload["run_id"] != expected.run_id:
        raise ValueError("run_id mismatch")
    if payload["nonce"] != expected.nonce:
        raise ValueError("nonce mismatch")
```

- [ ] **Step 4: Run the sandbox tests until they pass**

Run: `py -3.11 -m pytest tests/test_nova_release_sandbox.py -q`

Expected: pass with schema, nonce, run-id, digest, and oversized-payload rejection covered.

- [ ] **Step 5: Commit the sandbox contract**

```bash
git add -- src/nova_release_sandbox.py tests/test_nova_release_sandbox.py
git commit -m "feat: define sandboxed release result contract"
```

## Task 2: Add the guest bootstrap and Windows Sandbox launcher

**Files:**
- Create: `tools/nova_release_sandbox_guest.py`
- Modify: `src/nova_release_sandbox.py`
- Modify: `tests/test_nova_release_sandbox.py`

**Interfaces:**
- Consumes: `SandboxRunSpec`, guest-plan JSON, and the trusted gate definitions.
- Produces: `execute_guest_plan()`, `WindowsSandboxProvider.run()`, `.wsb` generation, and one guest result file.

- [ ] **Step 1: Write tests for guest-plan execution and launch failure**

```python
def test_guest_plan_execution_stops_on_first_failure():
    plan = {"run_id": "20260830T120000Z-abc123-00", "nonce": "n", "gates": []}
    result = execute_guest_plan(plan)
    assert result.gate_results[0].passed is False
    assert result.gate_results[1:] == []
```

- [ ] **Step 2: Run the guest-script tests to verify the bootstrap path is missing**

Run: `py -3.11 -m pytest tests/test_nova_release_sandbox.py -q -k guest`

Expected: fail until the guest bootstrap and launcher exist.

- [ ] **Step 3: Implement the guest bootstrap and sandbox launch path**

```python
def main(argv: Sequence[str] | None = None) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    result = execute_guest_plan(plan)
    write_json_atomic(Path(args.result), result.to_dict())
    return 0
```

- [ ] **Step 4: Run the focused sandbox tests**

Run: `py -3.11 -m pytest tests/test_nova_release_sandbox.py -q`

Expected: pass with `.wsb` generation, guest-plan execution, and host-side result loading all covered.

- [ ] **Step 5: Commit the sandbox launcher**

```bash
git add -- src/nova_release_sandbox.py tools/nova_release_sandbox_guest.py tests/test_nova_release_sandbox.py
git commit -m "feat: launch release gates inside Windows Sandbox"
```

## Task 3: Wire the sandbox into Release Lock and close the run-report TOCTOU gap

**Files:**
- Modify: `src/nova_release_lock.py`
- Modify: `src/nova_release_manifest.py`
- Modify: `tests/test_nova_release_lock.py`
- Modify: `tests/test_nova_release_manifest.py`

**Interfaces:**
- Consumes: `WindowsSandboxProvider`, `read_json_identity_pinned()`, and the existing `ReleaseRun` / `ReleaseStatus` flow.
- Produces: sandbox-backed `NovaReleaseLock.build()`, handle-pinned `NovaReleaseLock.load_run()`, and unchanged promotion/rollback behavior.

- [ ] **Step 1: Write regression tests that prove the controller now depends on the sandbox boundary**

```python
def test_build_fails_closed_when_sandbox_provider_is_unavailable(tmp_path: Path):
    class FailingSandboxProvider:
        def run(self, **_kwargs):
            raise RuntimeError("sandbox unavailable")

    lock = NovaReleaseLock(
        repo_root=repo,
        temp_root=tmp_path / "release-temp",
        sandbox_provider=FailingSandboxProvider(),
    )
    planned = lock.preflight()
    result = lock.build(planned)
    assert result.status is ReleaseStatus.FAILED
    assert result.failure_gate == "sandbox_unavailable"
```

- [ ] **Step 2: Run the release-lock tests to confirm the current shared-worktree path still exists**

Run: `py -3.11 -m pytest tests/test_nova_release_lock.py tests/test_nova_release_manifest.py -q`

Expected: the new sandbox assertions fail until the controller is wired through the provider and the safe reader exists.

- [ ] **Step 3: Implement the controller wiring and handle-pinned read helper**

```python
def read_json_identity_pinned(path: str | os.PathLike[str]) -> dict[str, object]:
    resolved = Path(path).resolve(strict=True)
    with resolved.open("r", encoding="utf-8") as handle:
        return json.load(handle)

class NovaReleaseLock:
    def build(self, run: ReleaseRun | str) -> ReleaseRun:
        sandbox_result = self.sandbox_provider.run(spec)
        if not sandbox_result.gate_results or not sandbox_result.gate_results[-1].passed:
            return self._fail(current, "sandbox_gate_failed")
```

- [ ] **Step 4: Re-run the controller and manifest suites**

Run: `py -3.11 -m pytest tests/test_nova_release_lock.py tests/test_nova_release_manifest.py -q`

Expected: pass with sandbox-backed verification, safe run loading, promotion unchanged, and path-swapped run reports rejected.

- [ ] **Step 5: Commit the controller integration**

```bash
git add -- src/nova_release_lock.py src/nova_release_manifest.py tests/test_nova_release_lock.py tests/test_nova_release_manifest.py
git commit -m "feat: verify release gates in Windows Sandbox"
```

## Task 4: Document the operator flow and run the focused release checks

**Files:**
- Modify: `docs/NOVA_RELEASE_LOCK.md`
- Modify: `docs/NOVA_COGNITIVE_OPERATING_LAYER.md`
- Modify: `tests/test_nova_release_lock.py`

**Interfaces:**
- Consumes: the completed sandboxed release controller and result contract.
- Produces: updated operator guidance, CLI expectations, and the final regression evidence for the release path.

- [ ] **Step 1: Write the operator-facing documentation checks**

```python
def test_release_lock_docs_mention_windows_sandbox_and_fail_closed():
    docs = (ROOT / "docs" / "NOVA_RELEASE_LOCK.md").read_text(encoding="utf-8")
    assert "Windows Sandbox" in docs
    assert "fail closed" in docs.lower()
```

- [ ] **Step 2: Run the release-lock and docs tests**

Run: `py -3.11 -m pytest tests/test_nova_release_lock.py tests/test_nova_release_manifest.py -q`

Expected: pass after the controller and safe reader are complete.

- [ ] **Step 3: Update the release docs and inline command references**

```md
Release verification runs inside Windows Sandbox on Windows.
If Sandbox is unavailable, the release fails closed.
```

- [ ] **Step 4: Run the targeted release smoke checks**

Run:

```powershell
py -3.11 -m pytest tests/test_nova_release_lock.py tests/test_nova_release_manifest.py -q
git diff --check
```

Expected: clean diff output and no release-lock regressions.

- [ ] **Step 5: Commit the documentation update**

```bash
git add -- docs/NOVA_RELEASE_LOCK.md docs/NOVA_COGNITIVE_OPERATING_LAYER.md tests/test_nova_release_lock.py
git commit -m "docs: document sandboxed release lock workflow"
```

## Self-Review

### 1. Spec coverage

- Windows Sandbox boundary and fail-closed policy: Task 1, Task 2, Task 3.
- Read-only inputs plus one writable output folder: Task 1 and Task 2.
- Strict guest result validation with run id, nonce, digest, and size checks: Task 1.
- Handle-safe run-report loading and TOCTOU closure: Task 3.
- Preservation of promotion and rollback semantics: Task 3.
- Operator guidance and visibility of the new workflow: Task 4.

### 2. Placeholder scan

- No `TBD`, `TODO`, or hand-wavy test instructions remain.
- Every implementation step includes a concrete file, command, or code shape.
- Every task has a commit step with exact files.

### 3. Type consistency

- `SandboxRunSpec`, `SandboxGateResult`, `SandboxRunResult`, `SandboxProvider`, `WindowsSandboxProvider`, `execute_guest_plan()`, `validate_sandbox_result()`, and `read_json_identity_pinned()` are introduced before later tasks depend on them.
- `NovaReleaseLock.build()` keeps the same public entry point, so existing CLI and tests remain compatible.
- `ReleaseRun` and `ReleaseStatus` are reused without renaming or splitting the promotion flow.
