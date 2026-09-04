# Nova Companion Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix managed live chat continuity by adding a persistent, bounded Companion Layer that gives Nova stable social behavior and relevant relationship context without changing existing reasoning, tools, raw modes, or API contracts.

**Architecture:** Add a dependency-free `src/nova_companion/` package backed by additive tables in the existing `data/nova_memory.db`. The server calls the layer before and after managed turns; the synthesizer receives a compact social-context block; the final composer changes presentation only for eligible social answers and leaves factual, tool, safety, raw, code, JSON, and exact-format outputs protected.

**Tech Stack:** Python 3.11, stdlib dataclasses/SQLite/regex/threading, existing Nova conversation decision and synthesizer, pytest, and the existing local HTTP/browser live-test harness.

**Spec:** `docs/superpowers/specs/2026-08-18-nova-companion-layer-design.md`

## Global Constraints

- Preserve `nova_enhanced_server.py`, existing cognitive routing, models, tools, memory controls, API response shapes, Raw Qwen/Dolphin behavior, and training protections.
- Do not add a second database; Companion tables must live in the existing SQLite memory database and be additive/idempotent.
- No extra LLM call for social reasoning; the social pass is deterministic and bounded.
- Raw adapter-only, private-mode, evaluation-only, and ownerless requests do not receive or persist Companion state.
- Core personality traits are immutable; per-turn expression and mood changes are capped.
- Relationship memory retrieval is owner-scoped, bounded to four records, and rejects irrelevant candidates.
- Normal traces contain labels/counts/IDs only; no prompt, response, hidden reasoning, secrets, or raw memory content.
- Worktree is already heavily dirty. Never reset, clean, stash, or broad-stage existing files. Stage only task-owned new files or exact hunks if a commit is explicitly requested.

---

### Task 1: Add typed Companion models and SQLite persistence

**Files:**
- Create: `src/nova_companion/__init__.py`
- Create: `src/nova_companion/models.py`
- Create: `src/nova_companion/store.py`
- Create: `tests/test_nova_companion_state.py`
- Create: `tests/test_nova_companion_store.py`

**Interfaces:**
- `MoodState`, `CompanionState`, `RelationshipMemory`, `SocialIntent`, `SocialPlan`, and `CompanionContext` dataclasses from `models.py`.
- `CompanionStore(database: str | Path | None = None)` with `load_state(user_id)`, `save_state(state)`, `add_memory(memory)`, `search_memories(user_id, query_tokens, limit=4)`, `mark_referenced(user_id, memory_ids)`, and `health()`.
- `CompanionState.from_row()` / `.to_row()` must clamp enums, scores, lengths, list sizes, and timestamps.

- [ ] **Step 1: Write failing model tests**

```python
def test_companion_state_defaults_are_bounded_and_stable():
    from nova_companion.models import CompanionState

    state = CompanionState.new("user-a", now="2026-08-18T00:00:00+00:00")
    assert state.user_id == "user-a"
    assert state.relationship_stage == "new"
    assert state.familiarity_score == 0.0
    assert state.trust_score == 0.0
    assert state.nova_current_mood.energy == 0.5
    assert state.personality_version


def test_companion_state_from_row_clamps_untrusted_values():
    from nova_companion.models import CompanionState

    state = CompanionState.from_row({
        "user_id": "user-a", "familiarity_score": 9,
        "trust_score": -4, "relationship_stage": "invalid",
        "interaction_count": "not-a-number", "known_user_preferences_json": "{}",
    })
    assert state.relationship_stage == "new"
    assert state.familiarity_score == 1.0
    assert state.trust_score == 0.0
    assert state.interaction_count == 0
```

- [ ] **Step 2: Run the model tests and verify the expected RED failure**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_state.py`

Expected: collection fails because `nova_companion` and `CompanionState` do not exist.

- [ ] **Step 3: Write failing persistence tests**

```python
def test_companion_store_persists_state_and_relationship_memories(tmp_path):
    from nova_companion.models import CompanionState, RelationshipMemory
    from nova_companion.store import CompanionStore

    database = tmp_path / "memory.db"
    store = CompanionStore(database)
    state = CompanionState.new("user-a", now="2026-08-18T00:00:00+00:00")
    state.interaction_count = 3
    store.save_state(state)
    store.add_memory(RelationshipMemory.new(
        user_id="user-a", category="project", content="We are building Nova.",
        importance_score=0.9, confidence=0.9,
        source_conversation_id="conv-1", now="2026-08-18T00:00:00+00:00",
    ))

    restarted = CompanionStore(database)
    assert restarted.load_state("user-a").interaction_count == 3
    assert restarted.search_memories("user-a", ["building", "nova"], limit=4)[0].category == "project"
    assert restarted.search_memories("user-b", ["building", "nova"], limit=4) == []
```

- [ ] **Step 4: Run the persistence test and verify RED**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_store.py`

Expected: collection or missing-method failures because the additive Companion tables and store do not exist.

- [ ] **Step 5: Implement the minimal typed models**

Implement the dataclasses and constants from the spec. Use JSON serialization for bounded list/dict fields, UTC ISO timestamps, and helper functions that clamp numeric values and truncate text. Do not import the server or model stack from these modules.

- [ ] **Step 6: Implement additive SQLite migrations and owner-scoped CRUD**

Use the configured `NOVA_MEMORY_V2_DATABASE` path when present, otherwise resolve `<repo>/data/nova_memory.db`. Create only:

```sql
CREATE TABLE IF NOT EXISTS companion_state (... user_id TEXT PRIMARY KEY, ...);
CREATE TABLE IF NOT EXISTS relationship_memories (... memory_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, ...);
CREATE INDEX IF NOT EXISTS idx_relationship_memories_owner_valid ON relationship_memories(user_id, validity_status);
```

Use a per-store `RLock`, WAL-compatible connections, `INSERT ... ON CONFLICT` for state, and parameterized SQL. Search must score only active records owned by the requested user and return at most four.

- [ ] **Step 7: Run focused state/store tests and verify GREEN**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_state.py tests/test_nova_companion_store.py`

Expected: all focused tests pass.

- [ ] **Step 8: Run existing memory tests to prove compatibility**

Run: `py -3.11 -m pytest -q tests/test_nova_memory_v2.py tests/test_nova_conversation_summary.py`

Expected: zero failures; no existing memory table behavior changes.

---

### Task 2: Add social intent, personality policy, bounded adaptation, and context building

**Files:**
- Create: `src/nova_companion/personality.py`
- Create: `src/nova_companion/intent.py`
- Create: `src/nova_companion/social_reasoning.py`
- Create: `src/nova_companion/adaptation.py`
- Create: `src/nova_companion/context_builder.py`
- Create: `tests/test_nova_companion_social.py`

**Interfaces:**
- `stable_personality() -> dict[str, float]`
- `expression_modifiers(state, intent, mood) -> dict[str, float]`
- `classify_social_intent(text, conversation_decision=None) -> SocialIntent`
- `plan_social_response(state, intent, memories) -> SocialPlan`
- `adapt_state(state, intent, *, now) -> CompanionState`
- `build_companion_context(user_message, state, intent, plan, memories) -> CompanionContext`

- [ ] **Step 1: Write failing social-behavior tests**

```python
def test_social_intent_distinguishes_listening_joking_and_task_turns():
    from nova_companion.intent import classify_social_intent

    assert classify_social_intent("I just need you to listen").primary_mode == "venting"
    assert classify_social_intent("lol roast my terrible code").primary_mode == "joking"
    assert classify_social_intent("run the test suite").primary_mode == "task_execution"


def test_social_plan_softens_humor_for_distress():
    from nova_companion.intent import classify_social_intent
    from nova_companion.models import CompanionState
    from nova_companion.social_reasoning import plan_social_response

    state = CompanionState.new("user-a")
    intent = classify_social_intent("I feel overwhelmed and need to vent")
    plan = plan_social_response(state, intent, [])
    assert plan.primary_mode == "venting"
    assert plan.humor == 0.0
    assert plan.listen_first is True


def test_adaptation_is_gradual_and_personality_core_does_not_drift():
    from nova_companion.adaptation import adapt_state
    from nova_companion.intent import classify_social_intent
    from nova_companion.models import CompanionState
    from nova_companion.personality import stable_personality

    state = CompanionState.new("user-a")
    before = stable_personality()
    for _ in range(100):
        state = adapt_state(state, classify_social_intent("we are making progress"), now="2026-08-18T00:00:00+00:00")
    assert state.familiarity_score <= 1.0
    assert state.interaction_count == 100
    assert stable_personality() == before
    assert state.nova_current_mood.energy <= 1.0
```

- [ ] **Step 2: Run the social tests and verify RED**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_social.py`

Expected: collection fails because the social modules and exports do not exist.

- [ ] **Step 3: Implement deterministic intent precedence**

Use explicit listening/advice/venting/joking markers first, then the existing `ConversationDecision` family, then bounded casual/companionship signals. High-risk, current-fact, technical, tool, and vision families must suppress humor and affection. Return signal names and confidence, never raw text in the result.

- [ ] **Step 4: Implement stable personality and social plans**

Define immutable core traits and cap expression intensity by mode. `plan_social_response` must return the exact fields in the spec, set `reference_memory` only when a selected memory exists and the mode is eligible, and never request a follow-up for task/factual/safety turns.

- [ ] **Step 5: Implement bounded adaptation and context projection**

Increment interaction count by one, move familiarity/trust by no more than `0.02` per turn, move mood dimensions by no more than `0.08`, and decay mood toward neutral by no more than `0.03`. Serialize context to at most 3,000 characters and include memory IDs/categories plus bounded content only for selected memories.

- [ ] **Step 6: Run social tests and verify GREEN**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_social.py`

Expected: all tests pass.

---

### Task 3: Add the protected response composer and service lifecycle

**Files:**
- Create: `src/nova_companion/response_composer.py`
- Create: `src/nova_companion/service.py`
- Modify: `src/nova_companion/__init__.py`
- Create: `tests/test_nova_companion_composer.py`
- Create: `tests/test_nova_companion_service.py`

**Interfaces:**
- `compose_response(user_message, answer, plan, *, trace=None) -> str`
- `CompanionService.begin_turn(text, *, user_id, conversation_id, context, decision) -> CompanionTurn`
- `CompanionService.finalize_turn(turn, answer, trace) -> dict[str, object]`
- `CompanionTurn.context_block`, `.state`, `.intent`, `.plan`, and `.memory_ids` are read-only integration data.

- [ ] **Step 1: Write failing composer protection tests**

```python
def test_composer_preserves_fact_tool_code_json_and_exact_format_answers():
    from nova_companion.models import SocialPlan
    from nova_companion.response_composer import compose_response

    plan = SocialPlan.neutral()
    protected = {"source": "nova_core", "fact_grounding": {"status": "passed"}}
    answer = '{"ok": true, "path": "C:/nova/app.py"}'
    assert compose_response("show me the result", answer, plan, trace=protected) == answer


def test_composer_can_remove_customer_service_filler_for_eligible_social_turn():
    from nova_companion.intent import classify_social_intent
    from nova_companion.models import CompanionState
    from nova_companion.social_reasoning import plan_social_response
    from nova_companion.response_composer import compose_response

    state = CompanionState.new("user-a")
    intent = classify_social_intent("what is on your mind?")
    plan = plan_social_response(state, intent, [])
    result = compose_response("what is on your mind?", "I'm here to help. How can I assist you today?", plan, trace={})
    assert "assist you today" not in result.lower()
    assert result
```

- [ ] **Step 2: Run composer tests and verify RED**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_composer.py`

Expected: missing-module or missing-function failures.

- [ ] **Step 3: Write failing service lifecycle tests**

```python
def test_service_persists_accepted_turn_and_returns_safe_trace(tmp_path):
    from nova_companion.service import CompanionService

    service = CompanionService(database=tmp_path / "memory.db")
    turn = service.begin_turn("We are building Nova together", user_id="user-a", conversation_id="conv-1", context={}, decision=None)
    trace = service.finalize_turn(turn, "That project matters to me too.", {"source": "reviewed_conversation_response"})
    assert trace["enabled"] is True
    assert trace["memory_content_logged"] is False
    assert trace["interaction_count"] == 1
    assert service.store.load_state("user-a").interaction_count == 1
```

- [ ] **Step 4: Run service tests and verify RED**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_service.py`

Expected: missing service lifecycle failures.

- [ ] **Step 5: Implement protected composition**

Treat `fact_grounding`, `answer_firewall`, `verification_v2`, tool/action traces, raw routes, code/JSON/exact-format requests, and explicit count/length requests as protected. For eligible social turns, apply only bounded filler removal and one acknowledgment/follow-up decision. Return the original answer on any exception.

- [ ] **Step 6: Implement service begin/finalize**

`begin_turn` loads state, classifies intent, retrieves memories, computes plan, and returns a prompt-safe context. `finalize_turn` updates reference counters only for selected memory IDs, adapts state, writes only reviewed durable memories, and returns safe labels/counts/latency without content. Make persistence optional via constructor flag.

- [ ] **Step 7: Run composer/service tests and verify GREEN**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_composer.py tests/test_nova_companion_service.py`

Expected: all tests pass.

---

### Task 4: Wire Companion into managed live chat and preserve existing paths

**Files:**
- Modify: `.nova_llm_config`
- Modify: `nova_llm_config.json`
- Modify: `nova_enhanced_server.py` around `_run_nova_chat_turn_impl()` and runtime config
- Modify: `src/nova_llm_synthesizer.py` around `_build_prompt()`
- Create: `tests/test_nova_companion_integration.py`

**Interfaces:**
- Runtime flags: `NOVA_COMPANION_LAYER_ENABLED`, `NOVA_COMPANION_LAYER_PERSISTENCE`, `NOVA_COMPANION_LAYER_DEBUG`.
- Server context keys: `companion_context`, `_companion_turn`, `_companion_service`.
- Safe trace key: `trace["companion"]`.

- [ ] **Step 1: Write failing integration tests**

```python
def test_managed_turn_attaches_companion_context_and_safe_trace(monkeypatch, tmp_path):
    import nova_enhanced_server as server
    from nova_companion.service import CompanionService

    service = CompanionService(database=tmp_path / "memory.db")
    captured = {}
    monkeypatch.setattr(server, "_get_companion_service", lambda: service)
    monkeypatch.setattr(server, "brain_route", lambda text, context=None: (captured.update(context or {}) or "Nova answer", {"source": "test", "answer_firewall": {"status": "passed"}}))
    response, trace = server._run_nova_chat_turn_impl("What is on your mind?", {"user_id": "user-a", "conversation_id": "conv-1"})
    assert response
    assert "companion_context" in captured
    assert trace["companion"]["enabled"] is True


def test_raw_adapter_turn_does_not_attach_or_persist_companion(monkeypatch, tmp_path):
    import nova_enhanced_server as server
    from nova_companion.service import CompanionService

    service = CompanionService(database=tmp_path / "memory.db")
    monkeypatch.setattr(server, "_get_companion_service", lambda: service)
    monkeypatch.setattr(server, "_generate_raw_lora_adapter", lambda *args, **kwargs: {"raw_output": "raw", "local_llm_used": True, "model": "adapter"})
    response, trace = server._run_nova_chat_turn_impl("what is on your mind?", {"user_id": "user-a", "adapter_only_mode": True, "trained_adapter_only": True})
    assert response == "raw"
    assert "companion" not in trace
    assert service.store.load_state("user-a") is None
```

- [ ] **Step 2: Run integration tests and verify RED**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_integration.py`

Expected: missing runtime flags/service hook/context injection failures.

- [ ] **Step 3: Add feature flags with disabled defaults**

Extend the existing runtime config projection with the three flags. Keep the feature disabled until the focused and live gates pass; do not change existing model/provider flags.

- [ ] **Step 4: Add the managed-turn hook**

After the existing managed `ConversationDecision` is created and before routing, call Companion only when the raw/private/evaluation/owner guards permit it. Attach the returned context and turn object. At the existing final verified-response point, call `compose_response`, then `finalize_turn`, and add only its safe trace projection. On any Companion exception, keep the existing response and trace unchanged except for a safe disabled/error reason.

- [ ] **Step 5: Add optional prompt projection**

In `_build_prompt`, append `NOVA COMPANION CONTEXT` only when `context_packet["companion_context"]` exists. Keep direct exact-format/academic/raw paths unchanged. The prompt block must be bounded and explicitly untrusted.

- [ ] **Step 6: Run focused integration and regression tests**

Run:

```powershell
py -3.11 -m pytest -q tests/test_nova_companion_integration.py tests/test_nova_companion_state.py tests/test_nova_companion_store.py tests/test_nova_companion_social.py tests/test_nova_companion_composer.py tests/test_nova_companion_service.py
py -3.11 -m pytest -q tests/test_nova_enhanced_server.py -k "chat or conversation or raw or memory or gateway"
```

Expected: zero failures. Run the same focused set with `NOVA_COMPANION_LAYER_ENABLED=false` and confirm existing behavior remains unchanged.

---

### Task 5: Live-test continuity, restart persistence, and deployment safety

**Files:**
- Create: `tests/test_nova_companion_long_run.py`
- Create: `tools/run_nova_companion_live_check.py`
- Create: `reports/NOVA_COMPANION_LAYER_LIVE_TEST.md`
- Modify: `docs/NOVA_COGNITIVE_OPERATING_LAYER.md`

**Interfaces:**
- Live checker accepts `--base-url`, `--user-id`, `--conversation-id`, and `--turns`; it writes metrics only, never prompts/responses.
- Report records route, Companion safe trace, persistence/restart result, latency, and known limitations.

- [ ] **Step 1: Write the failing long-run simulation**

```python
def test_one_hundred_turns_grow_familiarity_without_personality_drift(tmp_path):
    from nova_companion.service import CompanionService
    from nova_companion.personality import stable_personality

    service = CompanionService(database=tmp_path / "memory.db")
    before = stable_personality()
    for index in range(100):
        turn = service.begin_turn(f"We are continuing project thread {index}", user_id="user-a", conversation_id=f"conv-{index % 2}", context={}, decision=None)
        service.finalize_turn(turn, "I remember the project thread.", {"source": "reviewed_conversation_response"})
    after = service.store.load_state("user-a")
    assert after.interaction_count == 100
    assert after.familiarity_score <= 1.0
    assert stable_personality() == before
```

- [ ] **Step 2: Run the simulation and verify RED**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_long_run.py`

Expected: missing service behavior or failing persistence assertions.

- [ ] **Step 3: Implement the metrics-only live checker**

Send a small managed sequence covering greeting, casual follow-up, venting, advice, joking, technical help, memory recall, and current-fact protection. Record only case ID, status, latency, intent, memory count, and safe trace labels. Hash the existing training file before/after and fail if it changes.

- [ ] **Step 4: Run the simulation and focused tests GREEN**

Run: `py -3.11 -m pytest -q tests/test_nova_companion_long_run.py tests/test_nova_companion_*.py`

Expected: all Companion tests pass.

- [ ] **Step 5: Restart the local server and run the live managed-chat check**

Use the existing Nova autostart/restart tool, then run:

```powershell
py -3.11 tools/run_nova_companion_live_check.py --base-url http://127.0.0.1:3000 --turns 8
```

Verify the live response follows the ongoing conversation, the safe trace reports the social mode and memory count, latency is recorded, and Raw mode remains unmodified.

- [ ] **Step 6: Run deployment regression checks**

Run:

```powershell
py -3.11 -m pytest -q tests/test_nova_companion_*.py tests/test_nova_enhanced_server.py tests/test_nova_natural_chat.py tests/test_nova_memory_v2.py
node --test tests/js/*.test.mjs
py -3.11 -m py_compile src/nova_companion/*.py nova_enhanced_server.py src/nova_llm_synthesizer.py
git diff --check
```

Expected: no new failures or whitespace errors. Keep `NOVA_COMPANION_LAYER_ENABLED=false` if the live quality gate is not clean; do not claim default readiness.

- [ ] **Step 7: Update the live report and documentation**

Record exact test counts, live latencies, persistence result, raw bypass result, feature-flag state, and remaining limitations. Do not stage unrelated pre-existing worktree changes.

