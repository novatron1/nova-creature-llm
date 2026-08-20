# Validated Conversation Cascade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Nova's normal conversation route preserve valid context, retry weak answers safely, and prevent recovery text from recursively contaminating follow-ups.

**Architecture:** Add one context eligibility boundary, use it in bounded history/focus, and add a managed-turn state-commit guard around the existing candidate cascade. Keep deterministic action, current-fact, private, and raw-adapter gates unchanged.

**Tech Stack:** Python, pytest, Nova `/api/chat`, PowerShell live checks.

**Spec:** `docs/superpowers/specs/2026-08-19-validated-conversation-cascade-design.md`

## Global Constraints

- Preserve raw adapter, memory write, permission, safety, and current-fact behavior.
- Do not store raw dataset or prompt content in reports.
- Production code must be preceded by a failing regression test.
- Stage only the explicitly listed source, test, plan, spec, and sanitized report files.

---

### Task 1: Context eligibility boundary

**Files:**
- Modify: `src/nova_conversation_context.py`
- Test: `tests/test_nova_answer_firewall.py`

**Interfaces:**
- Produces `is_contextworthy_assistant_text(text: str) -> bool`.
- `bounded_conversation_history`, `previous_exchange`, and `conversation_focus` use the predicate.

- [x] **Step 1: Write the failing tests**

Add tests proving a generic firewall recovery answer is excluded from the latest exchange, while a normal contextual answer remains eligible and a trailing unanswered user turn is retained.

- [x] **Step 2: Run the focused tests and verify RED**

Run `py -m pytest -q -p no:cacheprovider tests/test_nova_answer_firewall.py -k "recovery or contextworthy or bounded_history"` and confirm the new assertions fail because recovery text is currently treated as assistant context.

- [x] **Step 3: Implement the smallest predicate and filtering**

Use bounded marker matching for known recovery/provider-error text. Do not import the firewall module into the context module. Apply the predicate only to assistant messages.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the same command and confirm all selected tests pass.

### Task 2: Non-recursive managed state commit

**Files:**
- Modify: `nova_enhanced_server.py`
- Test: `tests/test_nova_enhanced_server.py`

**Interfaces:**
- Produces `_conversation_turn_is_valid_for_commit(response, trace) -> bool`.
- `_run_nova_chat_turn` restores legacy state when the trace is a recovery/fact-blocked/provider-error result.

- [x] **Step 1: Write the failing tests**

Add tests that monkeypatch `_run_nova_chat_turn_impl` to return a blocked recovery and assert legacy state is unchanged; add a valid-answer case that commits the new exchange.

- [x] **Step 2: Run the tests and verify RED**

Run `py -m pytest -q -p no:cacheprovider tests/test_nova_enhanced_server.py -k "conversation_turn_is_valid_for_commit or state_commit"` and confirm the blocked case fails because the wrapper currently returns without a commit policy.

- [x] **Step 3: Implement the state-commit guard**

Snapshot legacy fields for every managed turn, call the existing implementation, inspect `final_answer_source`, `fallback_used`, and firewall status, then restore state for non-committable responses. Add privacy-safe trace fields `conversation_state_committed`, `conversation_state_commit_reason`, and `pending_turn`.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the same command and confirm both valid and blocked cases pass.

### Task 3: Contextual fallback and cascade observability

**Files:**
- Modify: `src/nova_answer_firewall.py`, `nova_enhanced_server.py`
- Test: `tests/test_nova_answer_firewall.py`, `tests/test_nova_enhanced_server.py`

**Interfaces:**
- `recovery_response(..., contextual_fallback=...)` remains backward compatible.
- Recovery traces identify `contextual_fallback` without exposing prompt content.

- [x] **Step 1: Write the failing tests**

Add a test proving a follow-up after a blocked primary uses a single contextual fallback and does not repeat a recovery marker. Add a trace test proving an alternate candidate attempt records its reviewer tier and rejection reason.

- [x] **Step 2: Run the tests and verify RED**

Run `py -m pytest -q -p no:cacheprovider tests/test_nova_answer_firewall.py tests/test_nova_enhanced_server.py -k "contextual_fallback or reviewer_tier or non_recursive"` and confirm the new assertions fail.

- [x] **Step 3: Implement the minimal fallback/cascade wiring**

Use the existing `resolve_followup` generation prompt and candidate selector. When all reviewers are unavailable, choose one bounded context-aware response, mark it as recovery, and prevent it from being written to valid state.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the same command and confirm all new assertions pass.

### Task 4: Full verification and live comparison

**Files:**
- Create: `reports/NOVA_VALIDATED_CASCADE_LIVE_TEST.json`
- Modify: none beyond Tasks 1–3

- [x] **Step 1: Run focused Python tests**

Run the three focused modules and record pass/fail counts.

- [x] **Step 2: Run broader conversation/server tests**

Run the relevant conversation, firewall, cognitive OS, gateway, and enhanced-server tests; report unrelated pre-existing failures separately.

- [x] **Step 3: Run live before/after route pack**

Exercise normal statement, clarification, referential follow-up, transform follow-up, current fact, and action guard through `http://127.0.0.1:3000/api/chat`. Record only case IDs, route labels, source labels, fallback recurrence, state-commit booleans, and latency.

- [x] **Step 4: Compile, diff, and privacy checks**

Run `py_compile`, `git diff --check`, inspect the staged diff, and confirm no model checkpoints, private logs, or raw prompts are staged.

- [x] **Step 5: Commit and push**

Stage only the listed source/tests/docs/report files, commit with `Fix validated conversation cascade`, and push the current feature branch to `origin` after fresh verification.
