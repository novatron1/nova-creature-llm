# Nova app repair: independent readiness check — September 6, 2026

Current subsystem checks passed with **295 passed, 0 failed, 0 errors, 12 skipped** in 245.87 seconds under Python 3.12.10. The live application conversation/latency test is separate; this report does not certify it or a production release.

Evidence: [current JUnit results](app-repair-readiness-20260906.xml). Pytest exited 0. Runtime logs, model warmup and automatic training were suppressed. No model generation, actual Windows Sandbox launch, server restart, storage deletion, source change, commit or promotion was performed by this audit.

The exact test files were:

```text
tests/test_nova_runtime_contracts.py
tests/test_nova_runtime_permissions.py
tests/test_nova_runtime_ledger.py
tests/test_nova_runtime_scheduler.py
tests/test_nova_runtime_memory.py
tests/test_nova_runtime_agent_report.py
tests/test_nova_runtime_eval_bank.py
tests/test_nova_runtime_end_to_end.py
tests/test_nova_runtime_verification_playwright.py
tests/test_nova_industrial_gate.py
tests/test_nova_identity_memory.py
tests/test_nova_release_gates.py
tests/test_nova_release_worktree.py
tests/test_nova_release_lock.py
tests/test_nova_release_policy.py
tests/test_nova_windows_sandbox.py
tests/test_nova_symlink_sandbox_proof.py
tests/test_nova_doctor.py
tests/test_nova_standalone_release.py
tests/test_nova_platform_coverage.py
```

Command: `python -m pytest <files above> -q --disable-warnings --tb=short -o faulthandler_timeout=60 --junitxml=reports/app-repair-readiness-20260906.xml`.

Eleven skips require Linux/POSIX. The twelfth is the Windows directory-symlink privilege test (`WinError 1314`). Skips are preserved in the result and are not counted as passes. Runtime end-to-end tests here use a fake browser fixture; they prove orchestration behavior rather than real-browser readiness.

`python tools/nova_doctor.py --port 3000` returned `ok: true`. Workspace, server file, Python and FFmpeg were present, and a TCP connection to `127.0.0.1:3000` succeeded. This checks installation and reachability, not chat response quality.

## Exact last release failure

The latest retained release run is `.git/nova-release-lock/runs/20260905T212229Z-7b7ab67766f0-3b71/`, whose status is `FAILED`. Its gate metadata identifies tested commit `2f942d7f4791477cfae1007a28729633bde5d7a7`. The current editing workspace remains at source HEAD `7b7ab67766f0ea0449292adf50a12560786c54ab` with uncommitted changes; current checks are not evidence for an immutable release commit.

In that retained run, the outer release-focused, dependency-lock, SBOM, JavaScript, application-acceptance and full-Python gates passed. The Industrial Gate failed. Its full Python phase recorded **2,288 passed, 0 failed, 12 skipped**; the failed verdict was due to unresolved coverage, not a failed Python assertion. Server regression (453), runtime contracts (54), memory/conversation (56), and release rollback (82) also had no failures.

The Industrial Gate report names three related blockers:

1. `unit_suite`: the host directory-symlink privilege skip lacked successful same-run replacement evidence.
2. `filesystem_symlink`: `Sandbox timed out without symlink evidence` (run `567ef683fb2139e07649abf6dad0ebfc`). Teardown reported that processes were not stopped and mapped files were not released.
3. `audit_error`: Windows `WinError 32` while removing the still-locked mapped input directory.

The detailed report is `.git/nova-release-lock/runs/20260905T212229Z-7b7ab67766f0-3b71/industrial-gate/report.json`. Its `promotion_allowed` is false. The evidence bundle is also retained under `E:/NovaVerification/20260904-industrial/nova-industrial-afkfrih9/`.

A separate earlier cleanup proof, `E:/NovaVerification/20260904-industrial/symlink-job-cleanup-final.json`, passed. That isolated result does not overwrite the later combined run's timeout/cleanup failure. Browser, rollback, terminal Sandbox, behavioral-baseline and managed identity-restart phases in the combined run passed, but their scope remains the fixtures described in `docs/NOVA_INDUSTRIAL_GATE.md`.

## Scope remaining

- The parent repair task must finish its fresh normal-chat sequence and verify continuity, response time, cancellation and displayed model status in the running app.
- Release promotion still requires a successful complete audit on the final unchanged candidate, including symlink evidence and cleanup. The current targeted pass does not bypass this requirement.

Independent review of the frontend repair found an asynchronous preflight double-submit race: the in-flight flag had been set after awaiting local navigation handling. The UI agent moved that claim before the await and added a deferred-command regression. Final code review found the claim/release paths, authenticated Stop request and collapsed diagnostics consistent; the UI agent owns its separate test results.

## Follow-up: cleanup defect isolated against the failed candidate

Compared the current `tools/nova_symlink_sandbox_proof.py` with the retained failed candidate at `E:/NovaVerification/20260904-industrial/release-lock/11c4fb93eb50/20260905T212229Z-7b7ab67766f0-3b71/candidate/`. The current workspace already contains fixes that the failed candidate did not:

- Failure cleanup now terminates the owned Job, waits for mapped input release, and records the result before returning.
- Release probes include the mapped directories, using `FILE_FLAG_BACKUP_SEMANTICS` when opening directory handles. The failed candidate probed only ordinary files and skipped mapping-release waits on the failure path.

Ran three existing cleanup regressions against the retained old module in an isolated test process: **3 failed**, reproducing the missing failure-path cleanup and directory-handle support. Ran the whole current symlink verifier test file: **19 passed, 0 skipped** in 0.45 seconds. No production module or test file was edited for this comparison. Evidence: `app-repair-symlink-old-code-regression-20260906.xml` (intentional old-code failure) and `app-repair-symlink-current-20260906.xml` (current code pass).

The earlier guest startup timeout remains unproven: the failed guest output directory is empty, with no bootstrap error or result; the phase exited after 184.765 seconds. The guest script, bootstrap, policy and product scanner hashes match the earlier successful standalone proof. Its retained JSON records successful Job teardown and mapping release, but that standalone artifact directory is no longer present. It cannot substitute for a new integrated proof.

No further source change is justified from this evidence. The known cleanup bugs are fixed in current code and have discriminating regressions; verifying that Sandbox actually starts, returns valid symlink evidence, and releases all mappings on the final candidate still requires a fresh real proof when the live-chat test is finished. No Sandbox launch was performed during this follow-up.
