# LLM-First Normal Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the configured LLM the default answer producer for ordinary conversation while preserving deterministic information and action routes.

**Architecture:** Add a narrow managed-chat policy decision after explicit memory/tool/current-fact gates and before canned conversational routes. Build a bounded, privacy-safe context packet for the LLM, then let existing answer firewall and fallback logic validate the generated answer. Keep the route trace as metadata only.

**Tech Stack:** Python 3.11, pytest, existing Nova gateway/server, configured local LLM synthesizer, PowerShell live smoke tests.

**Spec:** `docs/superpowers/specs/2026-08-20-llm-first-normal-chat-design.md`

## Global Constraints

- Preserve raw adapter mode and explicit tool/action route contracts.
- Preserve private-mode and memory read/write permissions.
- Canned recovery is allowed only after primary and fallback LLM attempts fail or are blocked.
- Do not stage unrelated dirty workspace files.

---

### Task 1: Lock the normal-chat policy with regression tests

**Files:**
- Modify: `tests/test_nova_enhanced_server.py`
- Modify: `tests/test_nova_conversation_intelligence.py` if shared decision coverage is needed

**Interfaces:**
- Consumes: `brain_route`, `_run_nova_chat_turn`, configured `nova_llm_synthesizer` seams, and existing trace fields.
- Produces: failing tests proving ordinary conversation uses an LLM candidate, preserves a follow-up subject, and leaves memory/tool/status routes deterministic.

- [x] **Step 1: Write failing tests** for an ordinary conversational prompt, a contextual follow-up, an explicit memory lookup, and an action/status prompt. Assert the ordinary response is the LLM candidate and does not contain planner/recovery markers.
- [x] **Step 2: Run the focused tests** and confirm the ordinary-chat assertions fail for the current route before the policy change.

### Task 2: Implement the LLM-first managed-chat policy

**Files:**
- Modify: `nova_enhanced_server.py`
- Modify: `src/nova_conversation_intelligence.py` only if the shared decision needs a precise normal-conversation subtype
- Modify: `tests/test_nova_enhanced_server.py`

**Interfaces:**
- Consumes: `conversation_decision`, bounded history, memory context, explicit tool/action route results, and existing LLM fallback helpers.
- Produces: a managed context packet and a trace policy field such as `normal_chat_policy="llm_first"` without changing client response shape.

- [x] **Step 1: Add the smallest context-packet helper** by extending the existing bounded cognitive context packet with explicit normal-chat answer instructions.
- [x] **Step 2: Place the policy after authoritative routes** and before generic canned conversation routes. Raw adapter mode and explicit/current/deterministic routes remain authoritative.
- [x] **Step 3: Send the packet through the existing configured LLM path** and retain the current firewall/repair/fallback ordering. Record `normal_chat_policy="llm_first"` only when the LLM path is used.
- [x] **Step 4: Run focused tests** and verify GREEN; no new generic response templates were added.

### Task 3: Run compatibility and live verification

**Files:**
- Modify: none unless a verified regression requires a targeted test or fix

**Interfaces:**
- Consumes: live local service on port 3000 and Tailscale remote endpoint.
- Produces: test evidence and synchronized GitHub commit.

- [x] **Step 1: Run targeted suites** for conversation intelligence, enhanced server routing, and fallback behavior.
- [x] **Step 2: Run the full enhanced-server suite**: 414 passed; one unrelated pre-existing Kaggle bundle fixture is missing `artifacts/nova_large_sft_dataset/train.jsonl`.
- [x] **Step 3: Restart the supervised service** and POST a live matrix covering normal conversation, contextual follow-up, dictionary, math, and status routes.
- [x] **Step 4: Verify local HTTP 200 and `git diff --check`; remote synchronization follows the scoped push below.**
- [x] **Step 5: Commit only the scoped source/tests/spec/plan files** with message `Make normal chat LLM-first` and push the active branch.
