# Normal Conversation Router Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve normal conversation routing for context-dependent follow-ups found in a large public dialogue sample without changing raw mode, memory writes, or safety gates.

**Architecture:** Audit OpenAssistant/OASST1 prompts in memory using the public dataset viewer, classify them with Nova's deterministic conversation-intelligence layer, and exercise representative prompts through the live `/api/chat` route. Add a small regression set for missing follow-up signals, then extend only the shared conversation classifier's precedence rules so follow-ups reach contextual continuation before generic fallback/model repair.

**Tech Stack:** Python, pytest, Nova `/api/chat`, Hugging Face datasets viewer API.

**Spec:** User request to practice normal conversation flow against a large online conversation dataset and fix incorrect routing.

## Global Constraints

- Do not commit the downloaded dataset or user conversation content.
- Do not alter raw adapter mode, private memory, training data, or action/safety gates.
- Preserve safe trace behavior: hashes/labels only, no prompt text in persisted reports.
- Production code must be preceded by a failing regression test.

---

### Task 1: Dataset route audit

**Files:**
- Read: `src/nova_conversation_intelligence.py`
- Read: `tools/run_nova_companion_live_check.py`
- Create locally only: temporary in-memory audit output (delete after verification)

- [x] Fetch a bounded English prompter sample from the Apache-2.0 OASST1 dataset viewer API.
- [x] Classify prompts with `understand_conversation_turn` and record only counts, labels, and hashed IDs.
- [x] Exercise representative follow-up, coding, factual, emotional, and open-ended prompts through `/api/chat` with content logging disabled.
- [x] Identify a repeatable misroute before writing a fix.

### Task 2: Follow-up routing regression

**Files:**
- Modify: `tests/test_nova_conversation_intelligence.py`
- Modify: `src/nova_conversation_intelligence.py`

- [x] Add tests for clarification, elaboration, referential “same/which of those,” and “more information” turns to expect `follow_up/contextual_continuation`.
- [x] Run the focused tests and verify the new assertions fail for the missing classifier behavior.
- [x] Add the smallest precedence rule covering explicit context-dependent follow-up markers.
- [x] Run the focused tests and verify they pass without changing existing social, memory, current-fact, or action precedence.

### Task 3: Live verification

**Files:**
- Create: `reports/NOVA_NORMAL_CONVERSATION_ROUTER_AUDIT.json` (sanitized labels/metrics only)
- Modify: none beyond Task 2

- [x] Run the focused conversation-intelligence and integration suites.
- [x] Run the live route sample again and verify follow-up turns report contextual continuation rather than generic fallback.
- [x] Run compile and diff checks; confirm no private/runtime data is staged.
- [x] Remove any temporary raw dataset files and report only sanitized metrics.
