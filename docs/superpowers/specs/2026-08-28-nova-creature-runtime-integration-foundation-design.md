# Nova Creature Runtime Integration Foundation Design

**Date:** 2026-08-28  
**Repository:** `C:\Users\nova\Documents\NOVA LLM CREATURE DESKTOP`  
**Status:** Draft for implementation planning

## 1. Purpose

Nova Creature already has substantial runtime pieces: permission-aware tools, provider routing, memory stores, media engines, browser-style verification hooks in tests, research schedulers, and durable JSON/JSONL persistence in multiple subsystems. The blocker is no longer invention. The blocker is integration.

This milestone creates a single runtime foundation that can carry one real autonomous job from start to finish:

1. read a project
2. modify it in an isolated workspace
3. run terminal tests
4. verify the result with Playwright
5. record the evidence and memory provenance
6. emit a structured agent report

The design ports the NovaMind control-plane ideas into Nova Creature as a canonical runtime layer, but only to the extent needed for the first end-to-end proof job. Later milestones can expand the same foundation into broader autonomy, more schedulers, and more eval coverage.

## 2. Existing System

The repository already contains many relevant building blocks:

- `src/nova_gateway/tools.py` — typed tool metadata, permissions, timeout handling, and execution.
- `src/nova_gateway/memory.py` — an adapter around long-term memory with explicit owner and mode controls.
- `src/nova_gateway/core.py` — provider routing, engines, budgets, and safe request orchestration.
- `src/nova_gateway/http.py` — the HTTP surface used by the desktop app and paired clients.
- `src/nova_gateway/structured.py` — bounded structured-output parsing and JSON-schema validation.
- `src/nova_gateway/mcp.py` — a deliberate MCP boundary that currently does not claim server/client runtime support.
- `src/nova_agent_loop.py`, `src/nova_agentic_core.py`, `src/nova_action_policy.py` — existing agent state, action gating, and authorization behavior.
- `src/nova_project_manager.py`, `src/nova_project_mod_agent.py`, `src/nova_code_sandbox.py` — project/workspace and modification support.
- `src/nova_release_worktree.py`, `src/nova_checkpoint_registry.py`, `src/nova_release_lock.py` — isolation, checkpointing, and release integrity patterns.
- `src/v404_research_scheduler.py`, `src/v405_research_priority_ranker.py`, `src/v406_research_safety_gate.py`, `src/v498_research_audit_log.py` — research scheduling and audit patterns, currently fragmented.
- `src/nova_quality_gate_agent.py` and browser-focused test assets — evidence-oriented verification patterns.
- `tests/test_nova_*` and `tests/js/*` — a large existing test corpus with route, memory, media, and UI coverage.

What is missing is a single canonical runtime contract that all of these subsystems can share without each subsystem inventing its own lifecycle, evidence format, or persistence semantics.

## 3. Scope of This Milestone

This release defines and implements the foundation needed for one verified autonomous job. It includes:

1. a canonical `RunContract`
2. a canonical `AgentRun` state machine
3. a universal tool/resource interface that is MCP-compatible in shape
4. an append-only evidence ledger with rollback points
5. provenance-aware memory writes
6. first-class Playwright verification
7. durable research task records and restart-safe scheduling
8. a focused behavioral eval bank
9. a structured final agent report
10. one end-to-end demo job that exercises the whole stack

This milestone does not attempt to replace every existing module. Instead, it introduces a stable orchestration layer and adapters around the existing gateway, tools, memory, and browser-verification code.

## 4. Goals

The release must:

1. Freeze each autonomous run in a machine-checkable contract before execution starts.
2. Represent tools and resources through one universal interface with MCP-like descriptors.
3. Drive each run through the state sequence `planned -> authorized -> executing -> verifying -> completed/failed/rolled_back`.
4. Persist an append-only evidence ledger with hashes, timestamps, and rollback anchors.
5. Capture memory with provenance fields: source, timestamp, confidence, owner, write reason, hash, previous version, and rollback point.
6. Make Playwright verification a first-class proof step with screenshots, DOM/assertion checks, console/network capture, and a failure trace.
7. Run research jobs from durable records that survive restart and enforce time, tool, and cost budgets.
8. Cover conversation quality, recall, planning, tool choice, refusal, self-correction, research accuracy, and multi-step completion with a dedicated eval bank.
9. Require every autonomous task to end with a structured agent report.
10. Demonstrate one real end-to-end job through the stack on the local machine.

## 5. Non-Goals

This milestone will not:

- build a full external MCP server/client implementation unless the internal adapter layer needs a minimal compatibility shim
- replace every legacy memory module at once
- rewrite the existing gateway or browser app from scratch
- make the system fully self-improving without human review
- add unrestricted network access to autonomous jobs
- store raw secrets, prompts, hidden reasoning, or full tool outputs in the ledger
- promise browser verification for arbitrary remote sites without the current Playwright/runtime prerequisites
- make the research scheduler a simple timer again; it must be durable task records or nothing

## 6. Design Principles

1. **One run, one contract, one ledger.**
2. **The model proposes; deterministic runtime code disposes.**
3. **Evidence beats generated text.**
4. **All autonomous actions must be replayable from recorded inputs and hashes.**
5. **Provenance is part of the data model, not an afterthought.**
6. **Adapters are allowed; duplicate runtimes are not.**
7. **Completion is a verified state transition, not a claim.**

## 7. Architecture

### 7.1 Canonical runtime flow

```text
User goal
   |
   v
RunContract builder
   |
   v
AgentRun created in "planned"
   |
   v
PermissionGateway / tool budget / workspace checks
   |
   v
authorized -> executing -> verifying
   |
   +--> evidence ledger append
   +--> provenance memory write
   +--> Playwright/terminal/resource verification
   |
   v
completed / failed / rolled_back
```

The new runtime layer sits above existing agent, gateway, tool, and verification components. Existing systems remain usable through adapters, but new autonomous work should flow through the canonical runtime first.

### 7.2 `RunContract`

`RunContract` is the immutable description of one autonomous job. It is created before the first action and must not be expanded by the job itself.

Required fields:

- `run_id`
- `goal`
- `goal_hash`
- `goal_summary`
- `owner_id`
- `project_id`
- `workspace_root`
- `allowed_roots`
- `network_mode`
- `shell_mode`
- `allowed_tools`
- `allowed_resources`
- `tool_permissions`
- `time_budget_seconds`
- `tool_budget`
- `cost_budget`
- `memory_budget`
- `evidence_policy_version`
- `verification_policy_version`
- `created_at`
- `contract_hash`

The contract is intentionally narrow. It describes what the run is allowed to do, where it is allowed to do it, and what proof is required for completion.

### 7.3 Universal Tool/Resource interface

The runtime needs one interface for tools and one for resources, both shaped so they can map cleanly to MCP-style descriptors later.

#### Tool

Each tool has:

- stable `tool_id`
- human-readable `name`
- `description`
- `category`
- `input_schema`
- `output_schema`
- `required_scopes`
- `risk_level`
- `read_write_classification`
- `confirmation_policy`
- `timeout_seconds`
- `supports_rollback`
- `supports_dry_run`
- `provider`
- `resource_dependencies`

Tool execution always goes through the permission gateway and emits ledger entries.

#### Resource

Each resource has:

- stable `resource_id`
- `uri`
- `resource_type`
- `owner_id`
- `scope`
- `content_classification`
- `read_only`
- `hash`
- `metadata`

Resources cover filesystem roots, terminal sessions, browser pages, GitHub repositories, research corpora, and any future external data source. The runtime may use adapters for local files, shell, browser, and GitHub, but the job sees one unified interface.

### 7.4 PermissionGateway

`PermissionGateway` is the deterministic gate between the contract and execution.

It must:

- compare each requested action to the frozen contract
- reject tool or resource use outside the allowed scope
- require approval for dangerous or externally visible actions
- enforce time/tool/cost budgets
- deny workspace escape
- deny network escalation
- bind approvals to the exact action signature

The gateway is the place where NovaMind's RunContract idea becomes concrete in Nova Creature. It is not a model. It is not advisory. It is the enforcement point.

### 7.5 AgentRun state machine

`AgentRun` tracks the runtime lifecycle and transitions:

- `planned`
- `authorized`
- `executing`
- `verifying`
- `completed`
- `failed`
- `rolled_back`

Allowed transitions:

- `planned -> authorized`
- `authorized -> executing`
- `executing -> verifying`
- `verifying -> completed`
- `executing -> failed`
- `verifying -> failed`
- `executing -> rolled_back`
- `verifying -> rolled_back`

Illegal transitions are rejected and recorded in the ledger.

Each state transition must store:

- prior state
- new state
- timestamp
- reason
- action signature when relevant
- evidence hash when relevant

### 7.6 Append-only evidence ledger

Every run writes an append-only ledger. The ledger must be hash-chained and content-redacted.

Ledger entries record:

- sequence number
- event type
- timestamp
- contract hash
- action signature
- resource hashes
- tool name
- verification result
- memory write result
- previous entry hash
- current entry hash

The ledger must never store:

- raw secrets
- tokens
- authorization headers
- hidden reasoning
- full tool outputs
- full prompt text when avoidable

The ledger is the canonical audit source for the run report.

### 7.7 Provenance-aware memory

Memory writes produced by autonomous jobs must be provenance-aware. A memory record must include:

- `source`
- `timestamp`
- `confidence`
- `owner`
- `write_reason`
- `content_hash`
- `previous_version_hash`
- `rollback_point`
- `ledger_entry_hash`

The memory system should store useful outcomes, not raw traces. A write may be rejected if the content is too vague, too sensitive, or lacks provenance.

This milestone does not replace the legacy memory systems immediately. It introduces a canonical provenance wrapper that the runtime uses for job writes, then adapts the existing stores under it.

### 7.8 Playwright verification

Verification is a first-class stage, not a side effect.

For browser-backed jobs, the verifier must collect:

- screenshot artifact
- DOM assertions
- console errors and warnings
- network request summary
- URL and navigation history
- failure trace when an assertion fails

The verifier must produce a typed result with:

- `passed`
- `failure_reason`
- `artifacts`
- `screenshot_hash`
- `dom_hash`
- `console_summary`
- `network_summary`
- `trace_hash`

The runtime should consider verification incomplete until these artifacts are recorded or the job is explicitly non-browser.

### 7.9 Durable research task scheduler

The existing research scheduler modules are useful but not durable enough for autonomous jobs. This milestone introduces durable task records with restart-safe scheduling.

Each research job record must include:

- `task_id`
- `run_id`
- `objective`
- `status`
- `attempt_count`
- `budget`
- `tool_budget`
- `time_budget_seconds`
- `cost_budget`
- `created_at`
- `updated_at`
- `next_retry_at`
- `last_heartbeat_at`
- `output_hash`
- `checkpoint_hash`

The scheduler must:

- resume after restart
- respect time/tool/cost budgets
- never continue past the frozen contract
- log retries and pauses to the ledger

### 7.10 Behavioral eval bank

The eval bank must cover the cases that keep failing in practice:

- conversation quality
- memory recall
- planning quality
- tool choice
- tool refusal
- self-correction
- research accuracy
- multi-step completion

Each eval case should have:

- a stable prompt
- expected runtime behavior
- required evidence
- pass/fail criteria
- regression tag

The eval bank is not a generic benchmark suite. It is a control system for the behaviors this runtime must preserve.

### 7.11 Structured agent report

Every autonomous task must end with a structured agent report. The report is the visible completion artifact for the human.

Required sections:

- goal
- plan
- tools used
- files changed
- tests executed
- browser evidence
- failures and retries
- final verification
- unresolved blockers
- rollback information

The report should be machine-readable as JSON and renderable as Markdown. It must point back to the ledger and verification artifacts by hash or path.

### 7.12 One end-to-end proof job

The first proof job for this milestone is intentionally narrow:

1. choose one real project in the repo
2. build a contract for a bounded modification
3. isolate the work in a dedicated workspace
4. read the target files
5. make the change
6. run terminal tests
7. open the result in Playwright
8. verify the UI or artifact visually and structurally
9. write provenance memory
10. produce the structured agent report

This proof job is the main acceptance target for the milestone. If the runtime cannot complete one bounded job end-to-end, the rest of the foundation is not yet ready.

## 8. Integration Points

### 8.1 Existing gateway and agent runtime

The new runtime layer should be introduced as a bounded orchestration layer above:

- `src/nova_gateway/core.py`
- `src/nova_gateway/http.py`
- `src/nova_gateway/tools.py`
- `src/nova_gateway/memory.py`
- `src/nova_agent_loop.py`
- `src/nova_agentic_core.py`

The existing HTTP and desktop surfaces should continue to work while the new runtime is added incrementally.

### 8.2 Existing project/workspace machinery

Workspace isolation should reuse the existing project, worktree, release, and checkpoint patterns instead of inventing a fresh filesystem model.

### 8.3 Existing browser verification patterns

The Playwright verifier should reuse the repository's existing browser verification conventions and test artifacts, but it must become a runtime service rather than a one-off test helper.

### 8.4 Existing research modules

Research scheduler work should absorb the behavior of the existing `v404`/`v405`/`v406`/`v498` family rather than duplicating them.

## 9. Verification Strategy

### 9.1 Unit tests

Create focused tests for:

- contract immutability and hash stability
- universal tool/resource descriptor validation
- permission-gateway action matching
- allowed and disallowed state transitions
- ledger append behavior and hash chaining
- provenance-aware memory writes and rollback point references
- Playwright verification result typing and artifact capture
- durable scheduler restart and budget enforcement
- eval bank loading and case classification
- structured report schema validation

### 9.2 Integration tests

Prove that:

- a bounded job can be contracted, authorized, executed, verified, and completed
- a denied action never reaches execution
- a write that mutates files records a rollback point
- a browser verification failure blocks completion
- a scheduler task resumes after restart
- a report cannot claim success without evidence

### 9.3 Live proof job

Run one real end-to-end job on the local machine:

- read a project
- change one file
- run tests
- verify with Playwright
- save provenance memory
- emit the structured agent report

Success requires a real artifact, real test output, and real verification evidence.

## 10. Rollout Plan

This milestone should be introduced in the following order:

1. contract and state machine
2. universal tool/resource interface
3. permission gateway and ledger
4. provenance-aware memory wrapper
5. Playwright verifier
6. durable research scheduler
7. eval bank
8. structured report
9. one live proof job

The runtime should remain useful after each step. The implementation should not wait until every piece is finished before any of it can run.

## 11. Planned File Boundaries

Likely new modules:

- `src/nova_runtime/contracts.py`
- `src/nova_runtime/permissions.py`
- `src/nova_runtime/interfaces.py`
- `src/nova_runtime/agent_run.py`
- `src/nova_runtime/ledger.py`
- `src/nova_runtime/memory_provenance.py`
- `src/nova_runtime/verification_playwright.py`
- `src/nova_runtime/research_scheduler.py`
- `src/nova_runtime/eval_bank.py`
- `src/nova_runtime/agent_report.py`

Likely adapter touchpoints:

- `src/nova_gateway/core.py`
- `src/nova_gateway/http.py`
- `src/nova_gateway/memory.py`
- `src/nova_gateway/tools.py`
- `src/nova_agent_loop.py`
- `src/nova_project_manager.py`
- `src/nova_project_mod_agent.py`
- `src/nova_quality_gate_agent.py`
- `nova_enhanced_server.py`
- `assets/nova_dream_studio.js`

Likely tests:

- `tests/test_nova_runtime_contracts.py`
- `tests/test_nova_runtime_permissions.py`
- `tests/test_nova_runtime_ledger.py`
- `tests/test_nova_runtime_memory.py`
- `tests/test_nova_runtime_verification_playwright.py`
- `tests/test_nova_runtime_scheduler.py`
- `tests/test_nova_runtime_eval_bank.py`
- `tests/test_nova_runtime_agent_report.py`
- `tests/test_nova_runtime_end_to_end.py`

## 12. Success Criteria

The milestone is complete when:

1. Nova Creature can create and persist a canonical `RunContract`.
2. One universal tool/resource interface can represent filesystem, terminal, browser, GitHub, and research.
3. An `AgentRun` advances through the required states without ambiguity.
4. The ledger is append-only and hash-linked.
5. Memory writes include provenance and rollback metadata.
6. Playwright verification produces screenshots, DOM assertions, console/network evidence, and a failure trace when needed.
7. Research jobs survive restart and enforce their budgets.
8. The behavioral eval bank exists and covers the required behavior classes.
9. Every autonomous task emits a structured agent report.
10. One real end-to-end proof job runs through the stack and verifies successfully on the local machine.

