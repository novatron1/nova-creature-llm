# Nova Release Lock

Nova Release Lock turns selected files from Nova's active development worktree
into a verified local release candidate without cleaning, resetting, stashing,
or committing the live worktree. It never pushes, deploys, restarts Nova, or
changes model weights, checkpoints, adapters, memories, databases, or secrets.

## Safety boundary

The authoritative boundary is
`config/nova_release_snapshot_policy.json`.

- Included: source, tests, tools, scripts, documentation, static assets,
  example configuration, dependency locks, and other explicitly listed code
  or release metadata.
- Excluded: Git internals, worktrees, attachments, caches, secrets, live
  configuration, databases, logs, reports, exports, backups, checkpoints,
  adapters, models, training data, memory, evidence, sandbox output, and model
  weight formats.
- Ambiguous: executables, dynamic libraries, installers, generic binaries,
  and ONNX files. Any ambiguous file stops the run for human review.
- Allowed static binaries are limited to the image, icon, and font suffixes in
  policy and remain subject to the configured size limit.

The source worktree is treated as read-only. Release Lock records its branch,
HEAD, and file classification; creates a separate Git worktree; overlays only
approved files there; scans and tests the candidate; and commits the manifest
inside the candidate. It fails if source HEAD or local `master` moves during
the run.

## Operator workflow

Run commands from the Nova repository root:

```powershell
py -3.11 tools\nova_release_lock.py plan
py -3.11 tools\nova_release_lock.py status --run-id <run-id>
py -3.11 tools\nova_release_lock.py build --run-id <run-id>
py -3.11 tools\nova_release_lock.py status --run-id <run-id>
py -3.11 tools\nova_release_lock.py promote --run-id <run-id>
py -3.11 tools\nova_release_lock.py cleanup --run-id <run-id>
```

With no subcommand, the CLI runs `plan`. The safe sequence is:

1. Run `plan`.
2. Open the reported `preflight.json` and inspect every inclusion, exclusion,
   and rule. Resolve any ambiguous item before continuing.
3. Run `build` with that exact run ID. Build creates the candidate and runs the
   configured release gates; it cannot change local `master`.
4. Run `status` and inspect `gates.json`, `run.json`, and the candidate
   `NOVA_RELEASE_MANIFEST.json`.
5. Inspect or test the candidate worktree directly.
6. Only after review, run the explicit `promote` command. This is the only
   Release Lock command that changes local `master`.
7. Run `cleanup` when the temporary worktrees are no longer needed.

CLI output is one JSON object. Exit code `0` means the requested operation
succeeded, `1` means a gate or build failed, and `2` means invalid input or an
unsafe repository state.

## Reports, worktrees, and references

Durable reports are stored in Git administrative data, not the candidate:

```text
<git-common-dir>/nova-release-lock/runs/<run-id>/
  preflight.json
  gates.json
  run.json
```

The default temporary root is the operating system's temporary directory under
`nova-release-lock/<repository-hash>/<run-id>/`. Override it with
`--temp-root` only when the directory is outside the protected repository and
is dedicated to Release Lock.

The candidate branch is `codex/release-lock-<run-id>`. Successful promotion
also creates `codex/rollback-release-lock-<run-id>` pointing to the exact
pre-promotion local `master` commit.

To inspect the candidate before promotion, read its path from `run.json`, then:

```powershell
git -C "<candidate-worktree>" status --short
git -C "<candidate-worktree>" log -1 --stat
py -3.11 tools\nova_release_lock.py status --run-id <run-id>
```

## Promotion guarantees

`promote` performs a local, explicit, no-fast-forward merge from the verified
candidate into local `master`. It refuses to run if the candidate is not in the
verified state, if its commit changed, if `master` moved, if `master` is checked
out in another worktree, or if the rollback reference already exists. A merge
conflict is aborted and local `master` is left unchanged and clean.

Promotion does not push to a remote, deploy files, start or stop the server,
restart Nova, or modify the live dirty source worktree.

## Failure recovery

- `PLANNED`: inspect the preflight report, then build or leave the run alone.
- `FAILED`: inspect `failure_gate`, `gates.json`, and `run.json`. Fix the source
  in the normal development workflow and start a new `plan`; do not edit a
  verified candidate in place.
- Interrupted build: use `status`; if the persisted state is not verified,
  treat the run as failed and start a new plan after inspection.
- Promotion conflict or unsafe state: Release Lock aborts before reporting
  success. Confirm `git status --short` for local `master` is empty and inspect
  `run.json` before retrying or starting a new run.
- After successful promotion, reverse the merge with the recorded merge commit:

```powershell
git -C "C:\path\to\NOVA LLM CREATURE DESKTOP" revert -m 1 <merge-commit>
```

This creates a new rollback commit and preserves history. Do not use
`git reset --hard` or a broad checkout in Nova's dirty development workspace.

## Cleanup semantics

`cleanup` removes only the candidate and promotion worktrees recorded for the
run after revalidating that they are strict children of the approved temporary
root. It never deletes the candidate branch, rollback reference, run reports,
manifest commit, source files, or local `master` history. Cleanup is therefore
safe after either inspection or promotion, while the durable audit trail
remains available.
