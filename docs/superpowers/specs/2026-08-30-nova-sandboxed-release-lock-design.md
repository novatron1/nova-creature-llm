# Nova Sandboxed Release Lock Design

**Date:** 2026-08-30

**Status:** Draft for implementation review

**Target:** Nova release verification and promotion

**Repository:** `NOVA LLM CREATURE DESKTOP`

## Purpose

Nova already has a release controller, deterministic manifests, path-safe storage,
and promotion/rollback logic. Its remaining release risk is that verification
gates still execute too close to the live workspace and still trust ordinary
file reads for persisted run state.

This design adds a stronger execution boundary for release gates on Windows by
running verification inside Windows Sandbox, while keeping the host release
controller responsible for source selection, result validation, and promotion.
The host must fail closed whenever the sandbox is unavailable, occupied, or
returns malformed evidence.

## Goals

1. Execute release gates in an isolated disposable guest on Windows.
2. Keep the live repository, credentials, clipboard, network, and host folders
   inaccessible to gate code.
3. Allow only explicitly approved read-only inputs and one writable output
   directory.
4. Validate guest output with strict schema, nonce, run-id, path, and digest
   checks before using it.
5. Prevent release-state TOCTOU by reading persisted run records through a
   handle-safe path rather than ordinary text reads.
6. Preserve existing promotion, rollback, and failure reporting semantics.

## Non-Goals

- Rewriting Nova’s cognition or agent loop.
- Turning the sandbox into a general-purpose runtime for arbitrary workloads.
- Allowing gate code to access the internet, host clipboard, host profiles, or
  host secrets.
- Falling back to an untrusted local process if Windows Sandbox is unavailable.
- Promoting guest-generated files directly without host validation.

## Selected Approach

Windows Sandbox is the primary verification boundary on Windows. The host builds
an approved input bundle, launches a disposable sandbox with a generated `.wsb`
file, and provides the guest only the minimum mounted inputs it needs.

The guest runs a trusted bootstrap script that copies the candidate and approved
runtimes into a VM-local workspace, executes gates under a restricted account,
and writes a bounded result record to a host-shared output folder. The host then
validates that result and decides whether to continue.

If Windows Sandbox cannot be started, or if the platform is not Windows, the
release fails closed. The design intentionally prefers no release over a weak
fallback.

## Architecture

### 1. Host Release Orchestrator

The host controller remains responsible for:

- identifying the candidate source revision;
- assembling the approved input bundle;
- generating the sandbox configuration;
- launching the sandbox;
- reading the guest result;
- validating the report against the expected run identity;
- committing and promoting only the original candidate tree after validation.

The host never trusts sandbox output as a source of truth until it has passed
validation.

### 2. Sandbox Guest

The guest is a disposable worker, not the primary release authority. Its job is
to:

- copy the approved candidate and trusted runtime bundle into guest-local
  writable storage;
- execute the configured gates;
- stop on first failure;
- capture bounded outputs and exit metadata;
- hash the candidate before and after the gates;
- emit exactly one structured result file.

The guest does not access the live repository, host credentials, or host-only
paths. It cannot promote anything by itself.

### 3. Result Integrity Layer

The host accepts only a strict result contract. The result record must include:

- schema version;
- run id;
- nonce;
- source commit;
- candidate digest before gates;
- candidate digest after gates;
- sandbox platform metadata;
- per-gate status records;
- bounded diagnostics.

The host rejects any result that:

- references the wrong run id or nonce;
- exceeds the expected file or payload size;
- contains unexpected paths;
- omits required fields;
- reports a candidate digest that does not match the pre-run candidate state;
- attempts to smuggle extra files or host paths into the report.

### 4. Handle-Safe Run State

Persisted run reports are read through a safe state accessor rather than plain
`Path.read_text`. The accessor must pin the target identity before reading and
reject path swaps, links, and reparse-point tricks.

This closes the TOCTOU hole where a report path could be swapped after
validation but before read.

## Sandbox Configuration

The generated Windows Sandbox configuration should disable or constrain:

- networking;
- clipboard redirection;
- printer redirection;
- audio input;
- video input;
- vGPU, unless explicitly required by a gate and separately approved;
- broad host-folder sharing.

The guest should receive only:

- a read-only mounted input folder containing the approved candidate bundle and
  trusted support files;
- one writable output folder for the result contract and logs.

The configuration should use `ProtectedClient` and a minimal memory budget that
still permits the declared test bundle to run.

## Gate Execution Model

The guest bootstrap may use a restricted non-admin user and job-style process
containment so child processes terminate with the gate runner.

Verification should proceed as follows:

1. Host writes the candidate bundle, runtime bundle, bootstrap script, and gate
   plan to the input area.
2. Host launches a disposable sandbox from the generated `.wsb`.
3. Guest bootstrap copies approved inputs into guest-local writable space.
4. Guest hashes the candidate state before running any gate.
5. Guest runs gates in order and stops on the first failure.
6. Guest hashes the candidate state again after the final gate.
7. Guest writes one bounded JSON result to the shared output folder.
8. Host validates the result and either continues or fails closed.

If the sandbox crashes, hangs, times out, or returns malformed evidence, the
host treats the run as failed.

## Promotion and Rollback

Promotion behavior does not change:

- only a verified run can be promoted;
- the original candidate worktree remains the source of truth;
- the host never promotes sandbox output;
- rollback references still point to the exact pre-promotion `master` commit.

Sandbox execution affects verification only. It does not loosen the current
Git-based promotion semantics.

## Platform Policy

- Windows: use Windows Sandbox when available; otherwise fail closed.
- Linux and macOS: fail closed for this release path.
- Future platform-specific sandbox providers may be added later, but only after
  they are designed and tested as explicit providers.

## Testing Strategy

Tests should cover:

- `.wsb` generation and disabled capability flags;
- sandbox launch configuration and host/output mount layout;
- guest result schema validation;
- nonce and run-id mismatch rejection;
- oversized and malformed output rejection;
- handle-safe run report loading;
- digest mismatch handling;
- fail-closed behavior when the sandbox is unavailable;
- promotion continuing to use the original candidate tree.

Integration tests should be structured so the sandboxed path can be exercised
with a fake provider when the host environment cannot start a real sandbox.

## Operational Behavior

- Release messages should say why the sandbox is unavailable or why the result
  was rejected, without exposing secrets.
- The result report should remain concise, bounded, and immutable after write.
- Any uncertain state should stop the release rather than downgrade the boundary.

