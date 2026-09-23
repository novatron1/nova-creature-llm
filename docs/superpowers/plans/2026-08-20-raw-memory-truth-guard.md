# Raw + Memory Truth Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Raw + Memory use verified memory and recover through Nova's LLM when the raw adapter invents or loops.

**Architecture:** Extend the existing raw-memory branch in `nova_enhanced_server.py`. A bounded memory resolver supplies a trusted prompt block; a provider-independent validator rejects unsupported memory claims/repetition; the existing strict LLM fallback helper supplies the final answer when raw retry fails.

**Tech Stack:** Python, pytest, existing Ollama/LoRA runtime, Nova trace dictionaries.

**Spec:** `docs/superpowers/specs/2026-08-20-raw-memory-truth-guard-design.md`

## Global Constraints

- Preserve Raw + Memory's no-tools and no-provider-fallback contract for generation.
- Never expose or persist unbounded memory content in a prompt or trace.
- Do not replace valid raw answers for ordinary non-memory prompts.
- The final fallback must be the configured LLM, not canned generic text.

### Task 1: Add failing memory-context and answer-validation tests

**Files:**
- Create: `tests/test_nova_raw_memory_truth_guard.py`
- Test: `tests/test_nova_raw_memory_truth_guard.py`

- [ ] **Step 1: Write tests for verified context, repetition rejection, unsupported-memory rejection, and LLM fallback.**

```python
def test_open_memory_question_builds_bounded_verified_context(monkeypatch): ...
def test_raw_memory_validator_rejects_repeated_filler(): ...
def test_raw_memory_validator_rejects_personal_claim_without_verified_memory(): ...
def test_raw_memory_retry_uses_llm_when_strict_retry_is_rejected(monkeypatch): ...
```

- [ ] **Step 2: Run the new file and confirm the helpers/behavior fail for the expected missing implementation.**

Run: `py -3.12 -m pytest -q -p no:cacheprovider tests/test_nova_raw_memory_truth_guard.py`

Expected: failures because the memory resolver/validator and guarded raw branch do not exist.

### Task 2: Implement verified memory context and the raw answer guard

**Files:**
- Modify: `nova_enhanced_server.py` in the raw-memory helpers and `_run_trained_adapter_only_request`.
- Test: `tests/test_nova_raw_memory_truth_guard.py`

- [ ] **Step 1: Add bounded memory-query detection and verified context rendering.**

Implement `_raw_memory_query_requested(text)` and `_raw_memory_verified_context(text, context)`. Use `ltm.recall_from_question` first, then at most eight active records from `ltm.get_all(active_only=True)`. Return an explicit no-match instruction when nothing is verified.

- [ ] **Step 2: Add deterministic raw-answer validation.**

Implement `_raw_memory_answer_guard(text, answer, verified_context)`. Reject repeated three-word phrases and reject confident personal-memory markers when the context says no verified memory. Return machine-readable reasons.

- [ ] **Step 3: Integrate one strict raw retry and the existing LLM fallback.**

For memory-shaped prompts, append a strict instruction to the raw prompt after a rejection. If the retry is rejected, call `_generate_llm_fallback_candidate` and return its answer with trace fields `raw_memory_guard`, `raw_memory_retry`, and `raw_memory_llm_fallback`.

- [ ] **Step 4: Run the new tests and confirm GREEN.**

Run: `py -3.12 -m pytest -q -p no:cacheprovider tests/test_nova_raw_memory_truth_guard.py`

Expected: all new tests pass.

### Task 3: Compatibility and live verification

**Files:**
- Modify: none beyond Task 2.
- Test: existing raw-memory and enhanced-server suites.

- [ ] **Step 1: Run focused compatibility tests.**

Run: `py -3.12 -m pytest -q -p no:cacheprovider tests/test_nova_enhanced_server.py -k "raw_memory or raw_adapter"`

- [ ] **Step 2: Restart the supervised server so the live process loads the guard.**

Stop only the `nova_enhanced_server.py` child; let `tools/nova_autostart.py` restart it.

- [ ] **Step 3: Run a live matrix of memory and non-memory Raw + Memory prompts.**

Verify that factual memory prompts show `raw_memory_guard` decisions, unsupported claims fall back to Nova LLM, and ordinary factual prompts remain raw adapter answers.

- [ ] **Step 4: Verify local/remote HTTP health and report exact evidence.**

Run: `Invoke-WebRequest http://127.0.0.1:3000/` and query `/api/gpu-hub/status`.
