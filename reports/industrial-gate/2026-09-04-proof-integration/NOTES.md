# Integration proof notes — September 4, 2026

This run is diagnostic, not release approval. Source changed during the run to fix test isolation/transport input and harden proof hashing; the audit must retain that blocker. No promotion was attempted.

Final combined verdict: all ten required phases produced evidence. Browser, rollback, Windows Sandbox and managed identity restart passed. Behavioral baseline scored 2/8 (0.25), below its 1.0 threshold. The early server phase retains its one transport-test failure; the corrected server/identity rerun below passed. Full-suite checkpoint failure/skips, changed source and dirty workspace also keep promotion blocked.

## Implemented

- Owner-scoped user names and assistant aliases, integrated into managed chat. Explicit renames persist; private/gateway restrictions apply.
- Actual Windows Sandbox terminal fixture with fresh nonce/run ID, bounded startup, strict output/hash verification and no host fallback.
- Installed local-model behavioral baseline: eight categories, recorded model digest/responses/tool traces, explicit protocol-versus-behavior failures and a strict release threshold.
- All three proof CLIs are invoked by Industrial Gate. Process failure or missing/false evidence blocks release; partial evidence is archived.
- Legacy checkpoint checks now exercise installed conversation-trained files and fail if required assets are absent, instead of silently skipping missing historical names.

## Verified separately on final changes

- Server plus identity regression: 425 passed (`reports/identity-server-regression-fixed.json`).
- Managed chat identity: 14 exact assertions across two fresh processes (`reports/identity-proof-final.json`).
- Gate evidence handling: 16 tests passed after final hash/read hardening.
- Sandbox verifier: 18 boundary tests passed; real guest proof passed on the 180-second retry (`reports/industrial-sandbox-proof-retry.json`).
- Full suite in this integration run: 2,239 passed, 1 failed, 12 skipped. The sole failure is checkpoint uniqueness: seven roles have three unique checkpoint files. This is retained as a failure, not repaired by arbitrary weight changes.

## Release limitations

The configured default/fast/active local model is qwen2.5:1.5b; qwen3:4b is configured for deep routing. The baseline explicitly tests the default connector, not every production route. Earlier live runs scored 2/8 and 1/8; use this run's archived behavioral report for its own result. A single scenario per category is only a baseline.

The 12 remaining skips require Linux execution or directory-symlink privilege. They remain blockers. The workspace also contains uncommitted source and private/runtime changes. Release-lock preflight classified 3,666 included paths and 28 excluded entries with no ambiguous entries, but did not build, commit, or promote a candidate (run `20260905T001056Z-7b7ab67766f0-6de3`). The release-lock currently commits after its gates; its sequencing still needs reconciliation with the Industrial Gate's clean-commit requirement before promotion can work.

Sandbox artifacts are copied under `sandboxed_terminal/sandbox-artifacts/<run_id>`. Absolute temporary paths inside original reports refer to their execution location; archived bytes are preserved unchanged. Sandbox proof establishes a generated terminal fixture, not a complete sandboxed production release suite. Network/clipboard restrictions are configured in the `.wsb`; no independent hostile guest connectivity test is claimed.

## Live application

Two verified older Nova processes on port 3000 were replaced by one fresh process running the updated source. `http://127.0.0.1:3000/` returned HTTP 200. Startup output is retained in `reports/runtime-refresh/`. Other port instances were left running. No merge, push, model download or weight modification was performed in this integration pass.
