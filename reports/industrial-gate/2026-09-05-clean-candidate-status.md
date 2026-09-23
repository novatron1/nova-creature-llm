# Clean candidate verification — September 5, 2026

The user authorized moving the unpacked export to F:. All four files were copied and SHA-256 verified before the original export directory was removed. The destination is `F:\NovaVerification\preserved-exports\NOVA_COMPANION_768D_LATEST_20260821`; its per-file receipt is `F:\NovaVerification\preserved-exports\unpacked-export-verification.json`. The ZIP remains alongside it. Active checkpoints remain in the source workspace.

Disposable work uses `E:\NovaVerification\20260904-industrial`. Its isolated `verification-venv` uses Python 3.12's installed dependencies with Pillow 12.3.0 installed locally in the environment, matching all three pinned core dependencies. Live Python installations were preserved.

Two private candidate attempts have failed safely; neither is promotable:

- `20260905T180456Z-7b7ab67766f0-9205`: runtime asset destination already existed. The scanner had pruned excluded directories without recording removals for files inherited from Git. The scanner now records those tracked exclusions without traversing private trees. Regression and focused review passed.
- `20260905T181243Z-7b7ab67766f0-3266`: release-focused tests, dependency lock, SBOM, JavaScript, and application acceptance passed. Full Python suite failed. The failure index contains 86 cases in four modules. Most depend on private/local test fixtures; server dictionary loading also needs to fall back to the shipped builtin dictionary. These corrections are in progress. Original evidence remains in the corresponding `.git/nova-release-lock/runs` directory.

The full Python gate now reserves and writes `python-full.xml`, retaining useful structured evidence even when its console capture is redacted. Two focused gate definition/artifact tests passed.

No final clean release commit has passed all gates. No merge, push, or promotion has occurred.

## Latest completed attempt

Run `20260905T184657Z-7b7ab67766f0-6ba4`, source snapshot commit `1e609b69265a969576b49bfade38e55fff87dc2f`, passed the first five release gates and the full Python suite (2,283 passed, 0 failed, 12 skipped). Its industrial audit began clean and all eleven required proof phases ultimately passed, including the strict 8/8 live model baseline and real Windows symlink proof. The eleven Linux/POSIX skips were classified not applicable on Windows, and the host symlink-permission skip was covered by that guest proof.

The audit nevertheless failed correctly during temporary-directory cleanup: Windows Sandbox still held `input/python/DLLs/libcrypto-3.dll` open after the helper returned. Failure is recorded as `audit_error` with WinError 32; the outer release remains FAILED at `industrial_gate`, with no candidate_commit. A bounded graceful Sandbox shutdown/file-release fix and an actual temporary-directory cleanup regression are in progress. Do not rewrite this failed report as success.

Additional completed corrections since the earlier attempts: private/runtime provenance JSONL is now explicitly ignored by Git; dictionary loading falls back to shipped defaults with local overrides; all 86 earlier clean-install failures and two new regressions passed diagnostically; worktree path-conflict validation uses normalized ancestor lookup and passed 52 tests. These changes were reviewed.

## Cleanup correction and current storage blocker

The first lifecycle correction waited for natural launcher exit. A real run produced valid guest evidence but timed out waiting for that exit; its surrounding temporary-directory cleanup succeeded after teardown. The launcher can stay open after the guest completes, so natural exit is not an adequate lifecycle signal. That diagnostic remains failed at `E:\NovaVerification\20260904-industrial\symlink-shutdown-cleanup-proof.json`.

The current helper instead reuses the existing pinned Windows Job containment primitive. It verifies guest evidence and input hashes, deliberately tears down only its owned process job, requires process cleanup success, waits for exclusive read-only access to all artifact files, then checks hashes again. It records deliberate teardown and process/file-release outcomes explicitly. Sixteen focused tests pass, including actual Windows file-sharing behavior; the revised nested Sandbox containment still requires a real run. No further Sandbox launch has been attempted.

C: currently has only about 200 MB free. Windows expanded its system-managed paging file to approximately 25.5 GB during this work. E: and F: were verified to be USB disks; no Windows paging configuration was changed. The user has been asked to save work and restart Windows (which may reclaim paging-file space), or otherwise free at least 10 GB on C:, before saying GO again. Both export relocations to F: are complete. No reboot or unrelated process termination was performed.

## Latest run and timeout cleanup correction

Run `20260905T212229Z-7b7ab67766f0-3b71`, private source snapshot `2f942d7f4791477cfae1007a28729633bde5d7a7`, remains FAILED. First five release gates passed; full Python suite recorded 2,288 passed, zero failed, 12 skipped. Industrial source inspection was clean. Browser, rollback, terminal Sandbox, strict live model behavior (8/8), and identity restart proofs passed. The final symlink guest timed out without evidence after its internal 180-second limit; temporary-directory cleanup also encountered a locked input directory. No final candidate commit was verified or promoted.

Before that run, the standalone owned-Job Sandbox proof passed, including removal of its surrounding temporary directory. Evidence: `E:\NovaVerification\20260904-industrial\symlink-job-cleanup-final.json`. Standalone and integrated guest payload hashes matched apart from the run-specific plan. Available Windows logs do not establish the cause of the integrated guest startup timeout. Disk pressure and nested containment require separate verification.

Confirmed code correction: failure paths now perform bounded owned-Job teardown and wait for exclusive access to mapped directories as well as files. Cleanup results/errors are recorded separately while preserving the original proof failure. Nineteen focused tests passed, including actual Windows directory-lock behavior and guest-timeout cleanup. Focused independent review found no actionable issues. No real Sandbox was launched after this correction because C: had only approximately 87 MB free.

At the latest GO, C: initially had approximately 13 GB free, then filled during verification. Its system-managed pagefile allocation is now 27,959 MB. The allocation at the start of that run was not measured, so the entire space loss cannot be attributed conclusively to the pagefile. E: and F: remain USB disks; Windows paging settings and unrelated processes were not changed. User was asked to recover at least 25 GB on C: before another guest launch.

Next verification should be a small symlink-only probe under two nested GateRunner wrappers, reproducing the integrated three Job layers, before repeating the full release pipeline. Record wrapper results, temporary-directory removal, C: free space and paging usage. A successful small probe still does not replace the required fresh clean-candidate release gates and final-commit verification.
