# Nova Release Gates POSIX PID Safety Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make failed POSIX release-gate launch cleanup incapable of signaling a process that reused the trusted supervisor's numeric PID.

**Architecture:** Capture a Linux PID file descriptor immediately after the trusted supervisor is spawned, before any `poll()` or `wait()` can reap it. Transfer that descriptor into failed-launch cleanup, signal only through that retained identity, and close it exactly once; if no retained descriptor exists after the supervisor is reaped, report incomplete cleanup without opening or signaling the numeric PID.

**Tech Stack:** Python 3.11 standard library (`os.pidfd_open`, `signal.pidfd_send_signal`, `subprocess`), pytest, Linux PIDFD semantics, existing `nova_release_gates` process-containment helpers.

## Global Constraints

- Do not modify, clean, reset, stage, or commit unrelated files in the live dirty worktree.
- Do not stop, restart, or reconfigure the running Nova server.
- Do not push branches, tags, or commits to a remote.
- Do not install new packages; use Python 3.11 standard library and existing project dependencies.
- Keep the remediation limited to failed POSIX launch identity retention and its regression coverage.
- Never signal a numeric PID or process group after the trusted supervisor has been reaped.
- Treat missing or indeterminate retained identity as incomplete cleanup and fail closed.
- Close every retained PIDFD on success and failure paths without masking the original launch classification.
- Never use `git reset --hard`, `git checkout --`, or an unchecked recursive delete.

## File Structure

### Modify

- `src/nova_release_gates.py` — acquire the supervisor PIDFD immediately after spawn, transfer it through failed-launch cleanup, and close it exactly once.
- `tests/test_nova_release_gates.py` — reproduce the already-reaped/PID-reuse window and verify retained-descriptor ownership and cleanup.

---

### Task 1: Retain Supervisor Identity Across Failed POSIX Launch Cleanup

**Files:**
- Modify: `src/nova_release_gates.py:1395-1458,1630-1735`
- Test: `tests/test_nova_release_gates.py:767-817,1195-1255`

**Interfaces:**
- Consumes: the `subprocess.Popen[bytes]` supervisor created by `_launch_contained_process()` and a PIDFD acquired immediately after `Popen` returns.
- Produces: `_terminate_failed_posix_launch(process, supervisor_descriptor) -> bool`, where cleanup owns and closes the optional descriptor and never reacquires identity from `process.pid`.

- [ ] **Step 1: Write the already-reaped PID-reuse regression test**

Add a focused unit test whose fake supervisor's first `poll()` returns an exit code, then instrument `os.pidfd_open`, `signal.pidfd_send_signal`, `process.kill`, and `os.killpg`. Call `_terminate_failed_posix_launch(supervisor, None)` and assert it returns `False` without opening a PIDFD for `4242` and without calling any numeric-PID or numeric-group signal path:

```python
def test_failed_posix_launch_does_not_reacquire_reaped_supervisor_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReapedSupervisor:
        pid = 4242
        returncode = 0

        def poll(self) -> int:
            return 0

        def wait(self, timeout: float) -> int:
            return 0

        def kill(self) -> None:
            raise AssertionError("must not signal a reaped numeric PID")

    opened: list[int] = []
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "pidfd_open", lambda pid: opened.append(pid), raising=False)
    monkeypatch.setattr(
        signal,
        "pidfd_send_signal",
        lambda descriptor, signum: sent.append((descriptor, signum)),
        raising=False,
    )
    monkeypatch.setattr(os, "killpg", lambda pgid, signum: pytest.fail("killpg"))
    monkeypatch.setattr(
        nova_release_gates._ProcessContainment,
        "_linux_cleanup_scan",
        lambda containment, deadline: nova_release_gates._LinuxSessionScan((), True),
    )

    assert nova_release_gates._terminate_failed_posix_launch(
        ReapedSupervisor(),  # type: ignore[arg-type]
        None,
    ) is False
    assert opened == []
    assert sent == []
```

- [ ] **Step 2: Run the regression and record strict RED**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/test_nova_release_gates.py -k "does_not_reacquire_reaped_supervisor_pid" -vv
```

Expected: FAIL because the current helper does not accept the retained descriptor and unconditionally calls `os.pidfd_open(process.pid)` after `poll()` can reap the supervisor.

- [ ] **Step 3: Add descriptor-transfer and exactly-once-close tests**

Add tests that pass a real harmless file descriptor as the retained identity, patch `signal.pidfd_send_signal` to record that exact descriptor, and patch `os.pidfd_open` to fail if called. Cover both a live fake supervisor and an already-reaped fake supervisor. Assert the helper uses only the supplied descriptor, closes it exactly once, returns `False` for indeterminate cleanup, and never falls back to `process.kill()` after reaping.

Also test `_launch_contained_process()` with injected `Popen` and launch failure boundaries to prove `os.pidfd_open(process.pid)` happens immediately after spawn, before payload writing, handshake polling, or waiting can reap the supervisor. The failure path must transfer ownership to `_terminate_failed_posix_launch`; the successful return path must close the setup-only PIDFD before returning `_ProcessContainment`.

- [ ] **Step 4: Implement the minimal retained-PIDFD flow**

In the POSIX branch of `_launch_contained_process()`, initialize `supervisor_descriptor: int | None = None`, acquire it immediately after `subprocess.Popen(...)`, and do not call `poll()` or `wait()` first:

```python
process = subprocess.Popen(...)
supervisor_descriptor = os.pidfd_open(process.pid)
```

Change failed cleanup to consume, never reacquire, the retained identity:

```python
def _terminate_failed_posix_launch(
    process: subprocess.Popen[bytes],
    supervisor_descriptor: int | None,
) -> bool:
    ...
```

Remove `os.pidfd_open(process.pid)` from `_terminate_failed_posix_launch()`. If the descriptor is present, signal via `signal.pidfd_send_signal(supervisor_descriptor, signal.SIGKILL)` and close it in one `finally` block. If the supervisor has already been reaped and the descriptor is absent, set `verified = False` and do not call `process.kill()`, `os.kill()`, or `os.killpg()` with its numeric identity. Transfer descriptor ownership to the helper by setting the caller's local variable to `None` after the call; on a successful launch, close the setup-only descriptor before returning.

Keep timeout/error classifications and bounded cleanup behavior unchanged.

- [ ] **Step 5: Run focused GREEN verification**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/test_nova_release_gates.py -k "failed_posix_launch or supervisor_pid or pidfd" -vv
```

Expected: all selected tests pass; Linux-only real-process proofs may be skipped on Windows.

- [ ] **Step 6: Run the complete Task 5 and broader release verification**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/test_nova_release_gates.py -q
python -m pytest tests/test_nova_release_policy.py tests/test_nova_release_security.py tests/test_nova_release_manifest.py tests/test_nova_release_worktree.py tests/test_nova_release_gates.py -q
python -m py_compile src/nova_release_gates.py tests/test_nova_release_gates.py
```

Expected: all available tests pass, with only explicitly platform-gated skips. Run the PIDFD-focused regression on Linux CI before Release Lock promotion.

- [ ] **Step 7: Review scope and commit**

Run:

```powershell
git diff --check
git status --short
git diff -- src/nova_release_gates.py tests/test_nova_release_gates.py
git add src/nova_release_gates.py tests/test_nova_release_gates.py
git commit -m "fix: retain release supervisor identity"
```

The commit must contain only the two authorized code/test files. A fresh reviewer must approve both specification compliance and code quality before the original Release Lock Task 5 is marked complete.
