# Nova Release Lock Design

**Date:** 2026-07-30

**Status:** Approved design

**Target:** Local Nova Creature source release

**Repository:** NOVA LLM CREATURE DESKTOP

## Purpose

Nova's current working directory contains a large mixture of committed source, valuable uncommitted application work, runtime data, local configuration, model artifacts, and generated files. The Release Lock creates a reproducible, test-verified source snapshot without modifying the live dirty workspace or exposing private local data.

The result is a locally committed release candidate that can be safely merged into local `master` only after every required gate passes. This process does not push to a remote repository, stop or restart the live Nova server, delete user files, or package model weights.

## Goals

1. Capture the approved Nova application source and supporting files from the current workspace.
2. Exclude secrets, private data, machine-specific state, large model artifacts, and generated content.
3. Build and test the snapshot in an isolated Git worktree.
4. Produce a deterministic manifest describing exactly what entered the release.
5. Fail before changing `master` when any file, security, or test result is uncertain.
6. Preserve a timestamped rollback reference before changing local `master`.
7. Leave the current live workspace and running Nova processes untouched.

## Non-Goals

- Pushing code or tags to GitHub or another remote.
- Reorganizing or rewriting the Nova application.
- Packaging or relocating model weights, adapters, checkpoints, or training data.
- Migrating personal memory, databases, conversations, or generated media.
- Cleaning, resetting, or committing the user's entire dirty workspace.
- Changing the active Nova model, provider, routes, memory behavior, or user interface.
- Deploying or restarting a server.

## Selected Approach

The release is built in a temporary clean Git worktree. This approach was selected over staging directly in the dirty workspace or producing only a portable archive.

The clean worktree provides a real Git candidate, isolates tests from unrelated runtime files, keeps the live application untouched, and permits a controlled local merge into `master`. A portable archive may be added later, but it is not the source of truth for this release.

## Architecture

Release Lock consists of four focused responsibilities.

### 1. Snapshot Policy

The policy classifies repository-relative paths as:

- `include`: approved source or release-supporting content.
- `exclude`: prohibited private, generated, machine-specific, or oversized content.
- `ambiguous`: content that cannot be classified safely and requires review.

The policy is deterministic, versioned, and machine-readable. Exclusion rules take precedence over inclusion rules. A path cannot enter the candidate merely because it was already tracked by Git.

### 2. Clean-Room Builder

The builder creates a timestamped release branch and temporary worktree from the current feature branch's committed `HEAD`. It then overlays the approved current-workspace files, applies intentional approved deletions, and removes files that the policy safely classifies as excluded.

Every candidate path is evaluated after the overlay, including previously tracked paths. An ambiguous path stops the process instead of being copied or deleted automatically. The builder does not modify the source worktree.

### 3. Release Verifier

The verifier checks the completed candidate tree rather than trusting only the copy operation. It scans for forbidden files, secrets, escaping symlinks, unexpected binaries, invalid configuration, dirty candidate state, and nondeterministic manifest output. It then runs the required test and smoke-test gates.

No gate may be marked successful based only on a planned or attempted action. The verifier records the observed command, exit status, duration, and concise output summary.

### 4. Release Manifest and Promotion Controller

The manifest records:

- Release identifier and timestamp.
- Policy and manifest schema versions.
- Source branch and source commit.
- Candidate branch.
- Included file paths, sizes, and SHA-256 hashes.
- Excluded categories and counts.
- Approved intentional deletions.
- Test and security-gate results.
- Runtime and dependency version information needed to reproduce verification.

The committed content manifest excludes its own path from its hash inventory, avoiding a self-referential hash. A separate run report is stored under Git's local administrative data rather than in a worktree. That report records the candidate commit after it exists, plus the final promotion or failure status.

The promotion controller creates a timestamped rollback reference for the current local `master`, then merges the verified candidate with an explicit merge commit from a separate clean worktree. Promotion is impossible while a required gate is incomplete or failed.

## Snapshot Boundary

### Included

- Application source under `src/`.
- Approved root Python server and application entry points.
- Web user-interface files and static assets required for startup.
- Launchers and maintainable operational scripts.
- Automated tests, evaluation definitions, and deterministic test fixtures.
- Development and release tools.
- Documentation.
- Version and application manifests.
- Dependency declarations and lockfiles.
- Sanitized example configuration files.
- Small static assets required for the application to start or render correctly.
- Existing tracked baseline files unless a higher-priority exclusion rule forbids them.

### Excluded

- `.nova_llm_config`, `.env`, and other real local configuration containing secrets or machine state.
- API credentials, authentication tokens, private keys, pairing secrets, and session credentials.
- Hardcoded absolute machine paths, usernames, or private network configuration in machine-local files.
- Model weights, quantized models, LoRA adapters, checkpoints, optimizer state, and training caches.
- Training datasets and user correction datasets.
- Personal memory, conversation databases, knowledge databases, feedback records, and routing logs.
- Application logs, audit logs containing private runtime data, and crash dumps.
- Generated images, video, audio, reports, and temporary exports.
- Python, browser, build, package-manager, and model caches.
- Remote attachments and temporary files.
- Binary installers and unapproved large binary artifacts.
- Files outside the repository.
- Symlinks or junctions whose resolved targets escape the repository.

### Ambiguous Content

Ambiguous files are never silently included. The preflight report lists each path and the classification reason. The release stops until the policy is updated or the file receives explicit review in a later run.

## Data Flow

1. **Preflight**
   - Confirm the repository, source branch, current commit, and local `master`.
   - Read the snapshot policy.
   - Enumerate tracked, modified, deleted, and untracked paths.
   - Resolve paths safely and reject repository escapes.
   - Generate include, exclude, deletion, and ambiguous lists.

2. **Candidate Construction**
   - Create a timestamped `codex/release-lock-*` branch at the feature branch's committed `HEAD`.
   - Create a temporary worktree for that branch.
   - Overlay only approved files from the live workspace.
   - Apply approved deletions.
   - Remove safely classified excluded files from the candidate, including forbidden tracked artifacts.
   - Refuse to continue if any ambiguous path remains.

3. **Manifest Draft**
   - Hash the candidate files in normalized repository-path order.
   - Record policy decisions, file counts, source revision, and environment diagnostics.
   - Exclude the content manifest's own path from its hash inventory.
   - Ensure regenerating the manifest from an unchanged tree yields the same content except for explicitly identified run metadata.

4. **Verification**
   - Run release-content, path, secret, and configuration checks.
   - Run automated Python, JavaScript, conversation-evaluation, and smoke-test gates.
   - Record observed results.
   - Regenerate and verify final hashes after all generated test artifacts have been excluded or cleaned.

5. **Candidate Commit**
   - Commit only the verified candidate contents and its final manifest to the release branch.
   - Confirm the candidate worktree is clean after the commit.
   - Record the resulting candidate commit in the separate local run report.

6. **Local Promotion**
   - Create a timestamped rollback branch or tag pointing to the pre-release local `master`.
   - Use a separate clean worktree for local `master`.
   - Merge the verified candidate commit using an explicit merge commit.
   - Verify the resulting `master` revision and record it in the release report.
   - Do not push.

The currently running Nova server and dirty feature worktree remain untouched throughout this flow.

## Failure Handling

Release Lock fails closed. These conditions stop the release before promotion:

- A secret or credential pattern is detected.
- A forbidden or unapproved binary enters the candidate.
- A symlink, junction, or resolved path escapes the repository.
- An ambiguous file remains unresolved.
- A required file is unexpectedly absent.
- The manifest cannot be reproduced deterministically.
- The candidate worktree is dirty at a required clean checkpoint.
- A security, unit, integration, evaluation, or smoke-test gate fails.
- Local `master` changes unexpectedly during the run.
- A rollback reference cannot be created.

On failure:

- The live source worktree and local `master` remain unchanged.
- The candidate is not promoted.
- A human-readable and machine-readable failure report identifies the failed gate.
- The failed worktree may be preserved for diagnosis; automatic cleanup is allowed only when its path is verified, it is inside the configured Release Lock temporary root, and preserving it is not needed for the failure report.
- No recursive delete or move is performed against an unresolved or unchecked path.

## Promotion and Rollback

Promotion is local and explicit. Release Lock must re-check that local `master` still points to the preflight revision before creating its rollback reference and merging.

The rollback reference uses a timestamped name and points to the exact pre-merge `master` commit. Promotion always creates a merge commit, even when Git could fast-forward, so the release report can supply one predictable non-destructive rollback command based on reverting that merge commit. Release Lock never runs a destructive reset automatically.

If promotion fails after the rollback reference is created, the tool reports both revisions and leaves recovery to an explicit follow-up action. It does not conceal a partial merge or claim success.

## Required Verification Gates

### Policy and Security

- Include, exclude, precedence, and ambiguous-classification unit tests.
- Path traversal and repository-escape tests.
- Symlink and junction escape tests where the platform supports them.
- Secret and private-data scanning.
- Unexpected binary and oversized-artifact checks.
- Example-configuration sanitization checks.
- Confirmation that model weights, adapters, checkpoints, training data, private memory, databases, attachments, and machine secrets are absent.
- Dependency-lock and existing release-security checks.

### Determinism and Git Isolation

- Stable normalized file ordering.
- Stable SHA-256 hashes.
- Manifest regeneration test.
- Clean-worktree construction test.
- Exact-source-overlay test.
- Candidate-only commit test.
- Source-worktree unchanged test.
- Local `master` unchanged on simulated failure.
- Rollback-reference creation test.

### Application Quality

- Complete Python test suite.
- Complete JavaScript test suite.
- The 560-case Nova conversation evaluation.
- Clean-start server smoke test.
- Health endpoint check.
- Local chat request.
- Companion request and conversational follow-up.
- Model-routing check.
- Memory read/write compatibility check using isolated test data.
- Image-path smoke check using deterministic fixtures.
- Mobile-layout and bottom-control regression checks.

Tests must use isolated temporary storage and configuration. They must not read or mutate the user's live private memory, training data, model files, or running application state.

## Operational Safety

- No remote push or external deployment occurs.
- No package installation occurs as part of a release run.
- No running process is stopped or restarted.
- No real API key is required or copied.
- No private prompt, response, memory content, or authentication header enters logs or manifests.
- The current dirty worktree is read as a snapshot source only.
- Git commands use explicit worktree paths and non-interactive behavior.
- Destructive Git commands such as `reset --hard` are not part of the workflow.

## User-Facing Outputs

Each run produces:

1. A preflight classification report.
2. A candidate branch name and worktree location.
3. A release manifest.
4. A gate-by-gate verification report.
5. A final result of `PROMOTED` or `FAILED`.
6. When promoted, the new local `master` commit and rollback reference.
7. When failed, the exact failed gate and safe next action.

Run reports are stored under Git's local administrative directory and are not added to the source snapshot. No output may expose secrets or private runtime content.

## Acceptance Criteria

Release Lock is complete when:

1. It deterministically classifies the current repository contents.
2. It fails on unresolved ambiguous files.
3. It constructs a candidate without modifying the live dirty worktree.
4. It proves prohibited content is absent.
5. It produces reproducible file hashes and a versioned manifest.
6. It runs every required verification gate and records observed results.
7. Simulated failures cannot change local `master`.
8. Successful promotion creates a rollback reference before merging.
9. It merges only a fully verified candidate into local `master`.
10. It never pushes, restarts Nova, deletes user data, or packages model/private artifacts.

## Future Extension

After Release Lock is reliable, the same verified candidate may become the input to a portable source archive, signed release, remote pull request, or installer pipeline. Those capabilities are intentionally outside this design and must not weaken the local snapshot policy or verification gates.
