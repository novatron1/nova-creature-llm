# Nova Professional Release Foundation Design

**Date:** 2026-08-10

**Status:** Approved design

**Target:** The first professional, locally distributable Nova Creature release

**Repository:** `NOVA LLM CREATURE DESKTOP`

## Purpose

Nova already has a large cognitive runtime, a provider-independent gateway, a polished Companion shell, extensive automated tests, model and memory integrations, and an existing Release Lock design. Its remaining release risk is not a lack of features. The risk is that the live workspace mixes valuable uncommitted source work with private runtime data and generated artifacts, conversational compatibility state is still shared globally in places, the latest measured Companion conversation gate passed only 17 of 25 cases, and no verified release candidate has been promoted from a clean snapshot.

This project establishes a professional release foundation without rewriting Nova's cognition, retraining models, deleting user data, changing the active model, or disrupting the running application. It turns the existing system into a reproducible, observable, session-safe release candidate with explicit promotion and rollback gates.

## Professional Release Definition

For this milestone, "professional" means all of the following are true:

1. A release is constructed from an explicit, secret-free source boundary rather than from the live mixed workspace.
2. Every promoted release has deterministic provenance, complete verification evidence, and a tested rollback path.
3. Simultaneous users, normal turns, and evaluation turns cannot overwrite or observe one another's transient conversation state.
4. Failures are bounded, privacy-safe, diagnosable, and represented honestly to callers and operators.
5. Companion is promoted to the default only after a fresh current-build quality gate passes; Classic remains available as a one-flag rollback.
6. A clean machine can install and start the source release using maintained documentation and declared dependencies.

This milestone does not claim that Nova's model is universally intelligent, that every external provider is available, or that native device features work without their required hardware and permissions.

## Scope

### In Scope

- Implement the approved Release Lock architecture described in `2026-07-30-nova-release-lock-design.md`.
- Introduce request-scoped and session-scoped runtime state behind a compatibility boundary for current Classic and Gateway consumers.
- Remove production request dependence on shared `_LAST_*` conversational fields while preserving controlled compatibility reads during migration.
- Establish privacy-safe structured operational events and a release-readiness report.
- Repair the eight failing cases from the latest measured 25-turn Companion acceptance run.
- Re-run the current-build automated, conversation, security, smoke, and live acceptance gates.
- Promote Companion only when every required gate passes.
- Preserve Classic and the existing `NOVA_COMPANION_DEFAULT` rollback mechanism.
- Produce maintained installation, operation, diagnosis, and rollback instructions for the verified source release.

### Out of Scope

- Model training, fine-tuning, quantization, adapter changes, or checkpoint modification.
- Replacing the current Cognitive OS, memory engines, provider gateway, or tool system.
- A full decomposition of `nova_enhanced_server.py`.
- Implementing the complete seven-component agentic architecture as a rewrite.
- Cloud deployment, public hosting, billing, telemetry export, or remote push.
- Deleting, relocating, packaging, or rewriting private memory, training data, model files, checkpoints, or generated media.
- Making Companion the default before release evidence passes.

The broader agentic architecture—perception, memory, reasoning/planning, tool execution, orchestration, guardrails, and observability—will be a later design cycle built on this release foundation. This milestone adds only the boundaries needed for release correctness and future extraction.

## Constraints

- The current dirty worktree is valuable user-owned state. It must not be cleaned, reset, bulk-staged, or overwritten.
- Existing unrelated modifications and untracked files must not enter commits made for this project.
- The running Nova server must not be stopped, restarted, or reconfigured without a later step that explicitly requires a bounded isolated smoke server or the user authorizes a live restart.
- Tests must use isolated configuration and temporary data stores. They must not mutate live memory, training data, model state, logs, or provider accounting.
- No secret, prompt, response, private memory value, authentication material, or personal path may enter a release manifest or readiness report.
- Release operations fail closed on ambiguous content, failed tests, path escapes, unsafe links, unexpected binaries, or incomplete evidence.
- Classic compatibility remains available throughout the milestone.

## Selected Approach

The selected approach is incremental release-first hardening.

Nova's existing behavior remains the baseline. New professional boundaries are added beside the current runtime and adopted through compatibility adapters. Release construction and verification happen in isolated worktrees. Session-state migration happens behind current request interfaces. Quality repairs are limited to the measured failing behaviors. Companion promotion is a final gated configuration change, not an early UI decision.

This approach is preferred over an immediate agent-core rewrite because it provides reproducibility and rollback before structural change. It is preferred over visual polish first because the Companion interface is already available and its blocking evidence is conversational quality and runtime isolation, not appearance.

## Architecture

The foundation has five components with narrow responsibilities.

### 1. Release Lock

Release Lock owns source classification, clean candidate construction, deterministic manifests, verification-gate execution, candidate commits, local promotion, and rollback references.

It consumes the approved snapshot policy and the current workspace as a read-only snapshot source. It produces a candidate branch, isolated candidate worktree, content manifest, local run report, gate results, and either `PROMOTED` or `FAILED` status.

The detailed component behavior, include/exclude rules, and Git safety invariants remain those of `2026-07-30-nova-release-lock-design.md`. This project does not weaken or duplicate those rules; it implements and integrates them as the release boundary.

### 2. Session Runtime State

Session Runtime State owns transient per-conversation values that are currently represented by process-global compatibility fields. Each state record is keyed by a validated local identity tuple:

- authenticated client identity when available;
- conversation identifier;
- session identifier.

The state record contains only bounded transient fields needed for continuity, cancellation ownership, routing context, and response composition. It does not replace persistent memory.

The store exposes acquire/read/update/clear operations and enforces bounded history, per-session locking, idle expiry, and a maximum record count. Different sessions can execute concurrently. Requests in the same session are serialized only where current cognition requires ordering.

A compatibility adapter may mirror the active request's values to legacy code while holding that request's compatibility lock, but production code must no longer use shared `_LAST_*` fields as authoritative cross-request storage. Evaluation state must never be visible to normal sessions.

### 3. Request Execution Boundary

The Request Execution Boundary creates one normalized execution context for every Classic, Gateway, Companion, and evaluation turn. The context includes:

- request and trace identifiers;
- validated client, conversation, and session identity;
- evaluation and retention policy;
- cancellation token and deadline;
- provider and cost constraints;
- permission and tool policy;
- transient session-state handle.

Existing cognition, memory retrieval, provider selection, tool execution, and answer-firewall behavior remain behind this context. The boundary is responsible for propagating cancellation, deadlines, evaluation restrictions, and session identity consistently. It returns a typed outcome distinguishing success, safe refusal, unavailable capability, cancelled work, timeout, and internal failure.

### 4. Readiness and Observability

Readiness and Observability records structured operational facts without storing content. Events may include:

- trace, request, session-hash, and route identifiers;
- start and completion timestamps;
- stage names and bounded durations;
- provider category and local/remote status;
- tool name and outcome category;
- memory-used Boolean without memory values;
- safety, cancellation, timeout, and fallback categories;
- response length, not response text;
- error class and sanitized error code, not raw secrets or payloads.

The readiness report combines release provenance and observed gate results. It must clearly distinguish `PASS`, `FAIL`, `BLOCKED`, `NOT RUN`, and `LIMITED`. A missing or stale result cannot be presented as a pass.

### 5. Companion Promotion Controller

The promotion controller changes the default interface only after all required current-build gates pass. It verifies that `/classic` remains available and that the configured rollback is exactly `NOVA_COMPANION_DEFAULT=false` followed by a normal restart.

Promotion does not remove Classic, change cognition, or migrate user data. If any gate fails, Companion remains available at `/companion` but is not the default.

## Data Flow

### Normal Request

1. The HTTP adapter authenticates or classifies the caller and validates request metadata.
2. The execution boundary creates a trace and normalized request context.
3. The session store acquires the matching transient state and required per-session lock.
4. Existing Nova cognition receives the normalized context and performs memory retrieval, reasoning, provider routing, and permitted tool operations.
5. Every proposed mutation or external action passes existing action, permission, evaluation, and safety policies.
6. The answer firewall validates the final response contract.
7. The session store commits only permitted bounded transient updates.
8. Observability records privacy-safe stage outcomes and durations.
9. The adapter returns a typed success or typed failure response.

### Evaluation Request

Evaluation follows the same path but sets non-retention and local/free-provider requirements before cognition begins. Memory mutation, training mutation, tools, filesystem/application actions, remote providers, and paid providers remain blocked. Evaluation state is held only inside its own session record and is discarded after the bounded run.

### Release Flow

1. Release Lock classifies the dirty workspace without modifying it.
2. Ambiguous paths stop the run for explicit policy review.
3. Approved source is overlaid into an isolated candidate worktree.
4. A deterministic content manifest is generated.
5. Security, unit, integration, JavaScript, conversation, smoke, and live-quality gates run against isolated state.
6. A passing candidate is committed on its candidate branch.
7. A rollback reference is created for local `master`.
8. The candidate is locally promoted with an explicit merge commit.
9. Companion default promotion occurs only when its independent promotion gates also pass.

## Error Handling

### Request Failures

- Invalid identity, evaluation flags, or permission metadata are rejected before provider or tool entry.
- Deadlines propagate to provider, tool, and streaming layers where supported.
- Cancellation is owned by the authenticated client and session; another session cannot cancel it.
- A timeout or cancellation stops result commitment and releases session resources.
- Provider or tool failures return a bounded user-safe outcome and a sanitized operational event.
- Partial paid streams preserve honest accounting and cannot double-charge terminal reconciliation.
- Persistent memory and training writes occur only after the applicable policy and successful stage boundary.

### Release Failures

- Ambiguous files, secrets, path escapes, unsafe links, unexpected binaries, missing required files, nondeterministic manifests, dirty candidates, or failed gates stop promotion.
- Failure never resets the source worktree or local `master`.
- A failure report identifies the exact gate, observed status, and safe next action.
- Cleanup is permitted only for a verified temporary path owned by Release Lock.

### Quality Failures

- Each of the eight known live failures becomes a stable evaluation case with a failure classification.
- Repairs target shared conversational mechanisms—continuity, correction handling, calibrated uncertainty, interruption, reconnect, and relationship tone—rather than hardcoded prompt-specific answers.
- If the current-build 25-turn gate remains below 25/25, the release report is honest and Companion promotion stays blocked.

## Privacy and Security

- Reports contain identifiers only after stable redaction or hashing.
- Prompt, response, memory, attachment, image, audio, token, and secret content is excluded from readiness and release reports.
- Remote evaluation clients cannot forge evaluation-only behavior or suppress accounting.
- Local evaluation requests cannot call remote or paid providers.
- Tool execution remains capability- and permission-gated.
- Release scanning covers credential patterns, forbidden private paths, unsafe links, unexpected binaries, and oversized artifacts.
- Example configuration is sanitized and real `.nova_llm_config`, environment files, pairing data, and provider credentials remain outside the release.

## Testing Strategy

### Unit Tests

- Snapshot classification, precedence, ambiguity, size limits, links, and path escapes.
- Deterministic manifest ordering and hashing.
- Session identity validation, isolation, expiry, bounds, and lock behavior.
- Evaluation versus normal session separation.
- Cancellation ownership and timeout outcomes.
- Structured-event redaction and readiness-state truthfulness.
- Companion promotion and rollback predicates.

### Integration Tests

- Concurrent Classic, Gateway, Companion, and evaluation turns with distinct sessions.
- Same-session ordering without cross-session serialization.
- Existing memory, provider, tool, cost, cancellation, and answer-firewall behavior through the execution boundary.
- Release candidate construction from a synthetic dirty repository.
- Candidate-only commits and source-worktree preservation.
- Simulated gate failures proving local `master` is unchanged.
- Clean-start server health, local chat, Companion, Classic, model routing, memory compatibility, and image-path smoke checks using isolated data.

### Required Release Gates

- Complete Python test suite.
- Complete JavaScript test suite.
- Python compilation and dependency declaration checks.
- Existing 560-case conversation evaluation in non-retaining mode.
- Fresh current-build 25-turn live Companion acceptance: 25/25.
- Training-data before/after hash: unchanged.
- Release-content, secret, path, binary, and configuration scans.
- Deterministic manifest regeneration.
- Clean candidate worktree after commit.
- Clean-machine installation/start procedure exercised in an isolated environment appropriate to the local platform.
- Classic route and one-flag rollback proof.

Historical test results are context only. Every promotion claim requires fresh results from the exact candidate being promoted.

## Delivery Sequence

### Milestone 1: Reproducible Candidate

Implement Release Lock and prove that a classified candidate can be built and verified without changing the live worktree or local `master`.

### Milestone 2: Session Isolation

Introduce the bounded session store and execution context, migrate the compatibility state, and prove concurrent-session isolation while keeping existing interfaces stable.

### Milestone 3: Quality and Diagnostics

Add privacy-safe operational events and readiness reporting, classify and repair the eight measured conversation failures, and run the complete candidate gates.

### Milestone 4: Controlled Promotion

Produce the verified source release, documentation, manifest, rollback reference, and readiness report. Promote Companion only if its exact current-build gates pass.

Each milestone must leave the repository in a testable state. A failed later milestone does not invalidate the completed safety guarantees of an earlier one.

## Maintained Documentation

The implementation must provide or update operator documentation covering:

- prerequisites and declared dependencies;
- sanitized configuration setup;
- clean start and shutdown;
- health and readiness interpretation;
- local model/provider availability;
- release preflight, build, verify, and promotion commands;
- common bounded failure recovery;
- Classic fallback and release rollback;
- explicit privacy boundaries and excluded user data.

## Acceptance Criteria

The professional release foundation is complete only when:

1. Release Lock deterministically constructs a secret-free candidate from the approved source boundary without modifying the live dirty workspace.
2. The exact candidate passes every required automated, security, conversation, smoke, and installation gate.
3. Concurrent sessions prove transient-state isolation, and production requests no longer rely on global `_LAST_*` fields as authoritative cross-request state.
4. Evaluation requests remain local, free, non-retaining, non-mutating, and isolated from normal sessions.
5. Readiness and diagnostic outputs contain no prompt, response, memory, secret, or attachment content and never convert missing evidence into a pass.
6. The fresh 25-turn Companion gate passes 25/25 on the exact candidate.
7. Classic remains reachable and the one-flag Companion rollback is re-proven.
8. The release includes maintained install, operation, diagnosis, and rollback instructions.
9. Promotion creates deterministic provenance and a rollback reference before changing local `master`.
10. No model, checkpoint, adapter, private memory, training dataset, or running user service is modified as part of the professionalization work.

If criteria 1–5 and 8–10 pass but criterion 6 fails, the foundation may be reported as technically verified but Companion promotion remains `BLOCKED`. It may not be described as a completed professional default release.

## Future Work

After this foundation is promoted, Nova can begin a separate design cycle that incrementally extracts perception, memory, reasoning/planning, tool execution, orchestration, guardrails, and observability from the monolithic compatibility runtime. That work will use the release manifest, session context, typed outcomes, and fresh quality gates created here as regression boundaries.
