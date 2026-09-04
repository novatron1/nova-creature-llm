# Nova Conversation Intelligence Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate seven live-tested upgrades that make Nova generalize conversational language, repair weak answers naturally, escalate models safely, preserve longer context, evaluate at least 500 language variations, fuse vision observations for safe navigation planning, and show stable answer-status information.

**Architecture:** A pure shared `ConversationDecision` is computed once for each managed turn and consumed by existing routing, grounding, response, recovery, model-selection, continuity, and UI layers. Existing Nova components are extended rather than replaced; raw adapter-only paths bypass every new managed-chat interception.

**Tech Stack:** Python 3.11 standard library, existing Pillow dependency, pytest, existing Nova HTTP server, existing gateway/provider registries, existing HTML/CSS/JavaScript mobile UI.

## Global Constraints

- Preserve `/api/chat`, Nova/OpenAI-compatible gateway routes, `brain_route`, the cognitive OS, natural chat, memory stores, training code, checkpoints, model weights, Ollama, and current working UI controls.
- Qwen 2.5 1.5B remains regular managed chat's default semantic model.
- Qwen 2.5 3B is the first practical local escalation tier.
- Dolphin 8B and Qwen3 14B run only when qualified and allowed by the existing RAM policy.
- Raw Qwen and Raw Dolphin adapter modes bypass the new decision, repair, and escalation interception.
- Do not install packages, download models, call paid services, or enable remote providers.
- Physical robot motor execution remains disabled; only observation, planning, and simulation are permitted.
- Do not persist prompt content, response content, hidden reasoning, raw sensor values, secrets, or API keys in safe traces.
- Every task must complete red/green tests, a server restart, a real live check, and neighboring regression tests before the next task.
- Use only backward-compatible configuration flags with safe defaults.

---

### Task 1: Shared Conversation Decision

**Files:**
- Create: `src/nova_conversation_intelligence.py`
- Create: `tests/test_nova_conversation_intelligence.py`
- Modify: `src/nova_turn_analyzer.py:20-55,176-250`
- Modify: `src/nova_intent_planner.py:172-210,328-370`
- Modify: `src/nova_fact_grounding.py:141-160,372-405`
- Modify: `nova_enhanced_server.py:_run_nova_chat_turn`

**Interfaces:**
- Consumes: raw user text and optional bounded conversation context.
- Produces: `ConversationDecision`, `understand_conversation_turn(text)`, `decision_from_context(context, text)`, and `ConversationDecision.safe_trace()`.
- Later tasks consume `ConversationDecision.repair_policy`, `initial_model_tier`, `expected_qualities`, `context_required`, and `intent_family`.

- [ ] **Step 1: Write failing decision and integration tests**

```python
from nova_conversation_intelligence import understand_conversation_turn


def test_social_paraphrases_share_one_relationship_decision():
    prompts = ("Did you miss me?", "Have u missed me", "Were you thinking about me?")
    decisions = [understand_conversation_turn(prompt) for prompt in prompts]
    assert {item.intent_family for item in decisions} == {"relationship"}
    assert all(item.factual_evidence_required is False for item in decisions)
    assert all(item.initial_model_tier == "deterministic" for item in decisions)


def test_current_fact_is_not_swallowed_by_social_generalizer():
    decision = understand_conversation_turn("Who is the current mayor of Detroit?")
    assert decision.intent_family == "current_fact"
    assert decision.current_information_required is True
    assert decision.factual_evidence_required is True


def test_raw_adapter_request_does_not_attach_managed_conversation_decision():
    context = {"trained_adapter_only": True, "adapter_only_mode": True}
    response, trace = server.brain_route("Did you miss me?", context=context)
    assert trace["source"] == "raw_adapter_only"
    assert "conversation_decision" not in trace
```

- [ ] **Step 2: Run tests and observe the missing-module/behavior failures**

Run:

```powershell
py -3.11 -m pytest -q tests/test_nova_conversation_intelligence.py
```

Expected: collection fails because `nova_conversation_intelligence` does not exist.

- [ ] **Step 3: Implement the pure shared decision**

Create the following public shape and deterministic precedence:

```python
from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Mapping

CONVERSATION_INTELLIGENCE_VERSION = "1.0"


@dataclass(frozen=True)
class ConversationDecision:
    intent_family: str
    intent_subtype: str
    dialogue_act: str
    context_required: bool
    factual_evidence_required: bool
    current_information_required: bool
    memory_recommended: bool
    reasoning_mode: str
    initial_model_tier: str
    repair_policy: str
    confidence: float
    expected_qualities: tuple[str, ...] = field(default_factory=tuple)
    signals: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = CONVERSATION_INTELLIGENCE_VERSION
    text_hash: str = ""

    def safe_trace(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "intent_family": self.intent_family,
            "intent_subtype": self.intent_subtype,
            "dialogue_act": self.dialogue_act,
            "context_required": self.context_required,
            "factual_evidence_required": self.factual_evidence_required,
            "current_information_required": self.current_information_required,
            "memory_recommended": self.memory_recommended,
            "reasoning_mode": self.reasoning_mode,
            "initial_model_tier": self.initial_model_tier,
            "repair_policy": self.repair_policy,
            "confidence": self.confidence,
            "expected_qualities": list(self.expected_qualities),
            "signals": list(self.signals),
            "text_hash": self.text_hash,
            "content_logged": False,
        }


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def understand_conversation_turn(text: str) -> ConversationDecision:
    canonical = re.sub(r"[^a-z0-9']+", " ", str(text or "").lower()).strip()
    if re.search(r"\b(?:current|latest|today's)\b", canonical) and re.search(
        r"\b(?:mayor|president|news|weather|price|score|ceo)\b", canonical
    ):
        return ConversationDecision(
            "current_fact", "volatile_lookup", "answer", False, True, True,
            False, "verify", "small", "strict_evidence", 0.98,
            ("fresh evidence", "source attribution"), ("volatile_entity",),
            text_hash=_hash_text(canonical),
        )
    if re.search(
        r"\b(?:did|do|have|would|were)\s+(?:you|u)\b.{0,24}\b(?:miss|think(?:ing)? about)\s+(?:me|us)\b",
        canonical,
    ):
        return ConversationDecision(
            "relationship", "connection_checkin", "answer", True, False, False,
            True, "fast", "deterministic", "reviewed_social", 0.97,
            ("warm", "honest", "relationship-aware"), ("relationship_phrase",),
            text_hash=_hash_text(canonical),
        )
    return ConversationDecision(
        "open_ended", "unknown", "answer", False, False, False, False,
        "fast", "small", "bounded_model_repair", 0.55,
        ("direct", "relevant"), ("fallback",), text_hash=_hash_text(canonical),
    )


def decision_from_context(context: Mapping[str, Any] | None, text: str) -> ConversationDecision:
    value = (context or {}).get("conversation_decision")
    if isinstance(value, ConversationDecision):
        return value
    return understand_conversation_turn(text)
```

Add explicit deterministic definitions for every intent family in the approved
design. Apply precedence in this order: permission/high-risk action, current
fact, memory command, vision/robot, project/tool, relationship/emotional/social,
follow-up, stable factual/reasoning, open-ended.

In `_run_nova_chat_turn`, compute and attach the decision only after the raw
adapter check:

```python
if not raw_adapter_request:
    conversation_decision = understand_conversation_turn(text)
    context["conversation_decision"] = conversation_decision
    context["conversation_decision_trace"] = conversation_decision.safe_trace()
```

Pass the safe trace into existing turn analysis. Update the planner and
grounding module to consume the shared decision before their legacy fallback
rules. Do not delete legacy rules until all consumers are migrated and tested.

- [ ] **Step 4: Run focused and neighboring tests**

```powershell
py -3.11 -m pytest -q tests/test_nova_conversation_intelligence.py tests/test_nova_turn_analyzer.py tests/test_nova_cognitive_os.py tests/test_nova_fact_grounding.py
```

Expected: all selected tests pass.

- [ ] **Step 5: Restart and live-fit Task 1**

POST these prompts through real `/api/chat`: `Did you miss me?`,
`How has your day been?`, `Why did you say that?`, `Who is the current mayor
of Example City?`, and one raw-adapter request. Verify decision family, managed
route, factual boundary, and raw bypass. Repair failures before continuing.

- [ ] **Step 6: Commit only Task 1 files**

```powershell
git add -- src/nova_conversation_intelligence.py src/nova_turn_analyzer.py src/nova_intent_planner.py src/nova_fact_grounding.py nova_enhanced_server.py tests/test_nova_conversation_intelligence.py
git commit -m "feat: add shared Nova conversation decision"
```

---

### Task 2: Natural Response Repair

**Files:**
- Create: `src/nova_response_repair.py`
- Create: `tests/test_nova_response_repair.py`
- Modify: `src/nova_cognitive_os.py:_fast_general_conversation_answer,route`
- Modify: `nova_enhanced_server.py:_run_nova_chat_turn`
- Modify: `src/nova_answer_firewall.py:FirewallDecision`

**Interfaces:**
- Consumes: `ConversationDecision`, rejected answer, `FirewallDecision`, and safe trace metadata.
- Produces: `RepairResult`, `reviewed_direct_response(decision)`, and `repair_rejected_response(...)`.

- [ ] **Step 1: Write failing reviewed-response and bounded-repair tests**

```python
from nova_answer_firewall import evaluate_answer
from nova_conversation_intelligence import understand_conversation_turn
from nova_response_repair import repair_rejected_response, reviewed_direct_response


def test_reviewed_relationship_response_is_warm_and_honest():
    decision = understand_conversation_turn("Were you thinking about me?")
    answer = reviewed_direct_response(decision)
    assert "connection" in answer.lower()
    assert "human" in answer.lower()
    assert "what do you want to do next" not in answer.lower()


def test_low_risk_generic_fallback_is_repaired_once():
    prompt = "How has your day been?"
    decision = understand_conversation_turn(prompt)
    rejected = "I'm here with you. Tell me what you want to do next."
    firewall = evaluate_answer(prompt, rejected, trace={"domain": "general_conversation"})
    result = repair_rejected_response(prompt, rejected, decision, firewall)
    assert result.repaired is True
    assert result.attempt_count == 1
    assert "day" in result.answer.lower()


def test_current_fact_repair_never_invents_evidence():
    prompt = "Who is the current mayor of Example City?"
    decision = understand_conversation_turn(prompt)
    firewall = evaluate_answer(prompt, "Jane Example is mayor.", trace={"domain": "current_facts"})
    result = repair_rejected_response(prompt, "Jane Example is mayor.", decision, firewall)
    assert result.repaired is False
    assert result.reason == "strict_evidence_required"
```

- [ ] **Step 2: Run tests and observe the missing-module failure**

```powershell
py -3.11 -m pytest -q tests/test_nova_response_repair.py
```

Expected: collection fails because `nova_response_repair` does not exist.

- [ ] **Step 3: Implement bounded reviewed repair**

```python
from dataclasses import dataclass
from nova_answer_firewall import FirewallDecision
from nova_conversation_intelligence import ConversationDecision

RESPONSE_REPAIR_VERSION = "1.0"


@dataclass(frozen=True)
class RepairResult:
    answer: str
    repaired: bool
    reason: str
    attempt_count: int
    source: str

    def safe_trace(self) -> dict[str, object]:
        return {
            "version": RESPONSE_REPAIR_VERSION,
            "repaired": self.repaired,
            "reason": self.reason,
            "attempt_count": self.attempt_count,
            "source": self.source,
            "content_logged": False,
        }


_REVIEWED_RESPONSES = {
    ("relationship", "connection_checkin"):
        "In my own way, yes. I don't feel absence like a human does, but I remember "
        "our conversations, value the connection we're building, and like having you back here.",
    ("nova_self_state", "day_checkin"):
        "My day is going steady. I've been here working through the app with you and "
        "staying focused. How's your day going?",
}


def reviewed_direct_response(decision: ConversationDecision) -> str:
    return _REVIEWED_RESPONSES.get((decision.intent_family, decision.intent_subtype), "")


def repair_rejected_response(
    prompt: str,
    rejected_answer: str,
    decision: ConversationDecision,
    firewall: FirewallDecision,
) -> RepairResult:
    if decision.repair_policy == "strict_evidence":
        return RepairResult(rejected_answer, False, "strict_evidence_required", 0, "none")
    reviewed = reviewed_direct_response(decision)
    if reviewed:
        return RepairResult(reviewed, True, "reviewed_intent_repair", 1, "reviewed")
    return RepairResult(rejected_answer, False, "no_deterministic_repair", 0, "none")
```

Use `reviewed_direct_response` in the cognitive fast path. In the managed
server, invoke `repair_rejected_response` before alternate-model escalation
only for low-risk firewall failures. Re-evaluate grounding, consistency, and
firewall on the repaired answer. Preserve strict recovery for current facts,
permissions, dangerous actions, tools, and unsupported completion claims.

- [ ] **Step 4: Run focused and firewall tests**

```powershell
py -3.11 -m pytest -q tests/test_nova_response_repair.py tests/test_nova_answer_firewall.py tests/test_nova_cognitive_os.py tests/test_nova_enhanced_server.py
```

Expected: all selected tests pass and existing strict recovery tests remain
unchanged.

- [ ] **Step 5: Restart and live-fit Task 2**

Live-test at least ten social paraphrases that previously produced generic
fallbacks, plus an unsupported current fact and a false tool-completion prompt.
Verify natural repair occurs once and strict cases remain blocked.

- [ ] **Step 6: Commit only Task 2 files**

```powershell
git add -- src/nova_response_repair.py src/nova_cognitive_os.py src/nova_answer_firewall.py nova_enhanced_server.py tests/test_nova_response_repair.py
git commit -m "feat: add bounded natural response repair"
```

---

### Task 3: Practical Small-to-Middle Model Escalation

**Files:**
- Modify: `src/nova_uncertainty_router.py`
- Modify: `src/nova_candidate_selector.py`
- Modify: `nova_enhanced_server.py:_direct_middle_model_decision,_generate_alternate_local_candidate,_run_nova_chat_turn`
- Modify: `src/nova_gateway/config.py`
- Create: `tests/test_nova_model_escalation_policy.py`

**Interfaces:**
- Consumes: `ConversationDecision`, request difficulty, firewall score/reasons, provider capabilities, and adaptive-memory policy.
- Produces: `EscalationDecision` and `decide_model_escalation(...)`.

- [ ] **Step 1: Write failing tier-policy tests**

```python
from nova_uncertainty_router import decide_model_escalation


def test_supported_social_turn_does_not_escalate():
    decision = decide_model_escalation(
        intent_family="relationship",
        difficulty_score=0.08,
        firewall_score=1.0,
        firewall_reasons=(),
        small_answer_available=True,
    )
    assert decision.should_escalate is False
    assert decision.selected_tier == "deterministic"


def test_relevant_but_incomplete_small_answer_uses_middle_before_deep():
    decision = decide_model_escalation(
        intent_family="open_ended",
        difficulty_score=0.42,
        firewall_score=0.58,
        firewall_reasons=("incomplete_answer",),
        small_answer_available=True,
    )
    assert decision.should_escalate is True
    assert decision.selected_tier == "middle"
    assert decision.fallback_tiers == ("middle", "deep")


def test_deep_model_denial_keeps_local_middle_fallback():
    result = server._generate_alternate_local_candidate(
        "Explain the tradeoff briefly.",
        primary_trace={"conversation_decision": {"intent_family": "open_ended"}},
        reviewer_tier="middle",
    )
    assert result["reviewer_tier"] == "middle"
    assert result["model"] in {"qwen2.5:3b", ""}
```

- [ ] **Step 2: Run tests and observe the missing policy API**

```powershell
py -3.11 -m pytest -q tests/test_nova_model_escalation_policy.py
```

Expected: import fails because `decide_model_escalation` is not defined.

- [ ] **Step 3: Implement explicit escalation decisions**

```python
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class EscalationDecision:
    should_escalate: bool
    selected_tier: str
    fallback_tiers: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_trace(self) -> dict[str, object]:
        return {
            "should_escalate": self.should_escalate,
            "selected_tier": self.selected_tier,
            "fallback_tiers": list(self.fallback_tiers),
            "reasons": list(self.reasons),
            "content_logged": False,
        }


def decide_model_escalation(
    *,
    intent_family: str,
    difficulty_score: float,
    firewall_score: float,
    firewall_reasons: Iterable[str],
    small_answer_available: bool,
) -> EscalationDecision:
    reasons = tuple(str(item) for item in firewall_reasons)
    if intent_family in {"greeting", "social_checkin", "relationship", "nova_self_state"}:
        return EscalationDecision(False, "deterministic", (), ("reviewed_intent",))
    if not small_answer_available or firewall_score < 0.75 or reasons:
        if difficulty_score < 0.68:
            return EscalationDecision(True, "middle", ("middle", "deep"), ("small_answer_quality",))
        return EscalationDecision(True, "deep", ("deep", "middle"), ("high_difficulty",))
    return EscalationDecision(False, "small", (), ("small_answer_accepted",))
```

Set the configured middle alias to `qwen2.5:3b`. Change quality-retry selection
so routine/relevant-but-incomplete failures qualify for middle before the
minimum deep-model byte threshold. Keep deep qualification and adaptive RAM
checks unchanged. Record every attempted tier and denial reason.

- [ ] **Step 4: Run routing, provider, and resource tests**

```powershell
py -3.11 -m pytest -q tests/test_nova_model_escalation_policy.py tests/test_nova_candidate_selector.py tests/test_nova_model_memory.py tests/test_nova_gateway_core.py tests/test_nova_enhanced_server.py
```

Expected: all selected tests pass; paid/remote and local-only tests remain
green.

- [ ] **Step 5: Restart and live-fit Task 3**

Live-test a greeting, ordinary small-model question, incomplete-answer repair,
moderate comparison, and deep architecture prompt. Confirm no social
escalation, middle-before-deep retry, RAM-policy denial without freezing, and
no remote calls.

- [ ] **Step 6: Commit only Task 3 files**

```powershell
git add -- src/nova_uncertainty_router.py src/nova_candidate_selector.py src/nova_gateway/config.py nova_enhanced_server.py tests/test_nova_model_escalation_policy.py
git commit -m "feat: route weak small-model answers through middle tier"
```

---

### Task 4: Conversation Continuity Ledger

**Files:**
- Modify: `src/nova_conversation_summary.py`
- Modify: `src/nova_conversation_context.py`
- Modify: `src/nova_gateway/world_model.py`
- Modify: `src/nova_gateway/core.py`
- Create: `tests/test_nova_conversation_continuity_ledger.py`

**Interfaces:**
- Consumes: client-scoped recent messages, existing `ConversationSummary`, shared decision safe trace, and response trace.
- Produces: versioned `ContinuityLedger` fields in summaries and safe world-model views.

- [ ] **Step 1: Write failing continuity and isolation tests**

```python
from nova_conversation_summary import ConversationSummary, roll_conversation_summary


def test_summary_keeps_unanswered_user_question_and_nova_commitment():
    update = roll_conversation_summary(
        ConversationSummary(),
        [
            {"role": "user", "content": "Why did you say the Earth evidence was strong?"},
            {"role": "assistant", "content": "I'll explain the strongest checks next."},
        ] * 6,
        "Okay",
        "Let's continue.",
        keep_recent_messages=4,
    )
    assert any("Why did you say" in item for item in update.summary.unresolved_questions)
    assert any("explain" in item.lower() for item in update.summary.commitments)


def test_world_model_keeps_clients_isolated_without_prompt_content(tmp_path):
    model = NovaWorldModel(persistence="checkpoint", checkpoint_path=tmp_path / "world.json")
    model.record_continuity("phone", "c1", {"active_topic": "relationship", "unresolved_count": 1})
    model.record_continuity("desktop", "c1", {"active_topic": "coding", "unresolved_count": 0})
    assert model.view("phone", "c1")["continuity"]["active_topic"] == "relationship"
    assert model.view("desktop", "c1")["continuity"]["active_topic"] == "coding"
    assert "prompt" not in (tmp_path / "world.json").read_text(encoding="utf-8").lower()
```

- [ ] **Step 2: Run tests and observe missing fields/methods**

```powershell
py -3.11 -m pytest -q tests/test_nova_conversation_continuity_ledger.py
```

Expected: failures for missing `unresolved_questions`, `commitments`, and
`record_continuity`.

- [ ] **Step 3: Add bounded versioned continuity fields**

Extend `ConversationSummary` with:

```python
unresolved_questions: tuple[str, ...] = field(default_factory=tuple)
commitments: tuple[str, ...] = field(default_factory=tuple)
corrections: tuple[str, ...] = field(default_factory=tuple)
active_entities: tuple[str, ...] = field(default_factory=tuple)
emotional_context: tuple[str, ...] = field(default_factory=tuple)
```

Detect user questions by terminal question mark or interrogative dialogue act.
Close matching loops when the next assistant response is direct and not a
clarification/recovery. Detect commitments only from bounded phrases such as
`I'll`, `I will`, `next I`, and `we can`. Treat restored summary text as
untrusted context.

Add `NovaWorldModel.record_continuity(client_id, conversation_id, value)` that
persists only allowlisted labels, counts, and state enums:

```python
def record_continuity(self, client_id: str, conversation_id: str, value: dict[str, Any]) -> dict[str, Any]:
    board = self._get_or_create(client_id, conversation_id)
    board.continuity = {
        "active_topic": _safe_choice(value.get("active_topic"), _SAFE_TOPICS, "general_conversation"),
        "unresolved_count": max(0, min(int(value.get("unresolved_count") or 0), 8)),
        "commitment_count": max(0, min(int(value.get("commitment_count") or 0), 8)),
        "last_answer_type": _compact(value.get("last_answer_type"), 40),
    }
    self._save_checkpoint()
    return dict(board.continuity)
```

Call it from gateway completion after conversation summary update. Preserve
checkpoint migration support for schema 1.0 and 1.1 while bumping the world
model schema to 1.2.

- [ ] **Step 4: Run summary, context, world-model, and gateway tests**

```powershell
py -3.11 -m pytest -q tests/test_nova_conversation_continuity_ledger.py tests/test_nova_conversation_summary.py tests/test_nova_world_model.py tests/test_nova_gateway_core.py tests/test_nova_enhanced_server.py
```

Expected: all selected tests pass, including checkpoint migration and privacy.

- [ ] **Step 5: Restart and live-fit Task 4**

Use two client IDs with the same conversation ID. Run an eight-turn phone
conversation with an unresolved relationship question and an independent
desktop coding conversation. Restart Nova, continue both, and verify topic,
pronoun/follow-up resolution, isolation, and privacy-safe checkpoint content.

- [ ] **Step 6: Commit only Task 4 files**

```powershell
git add -- src/nova_conversation_summary.py src/nova_conversation_context.py src/nova_gateway/world_model.py src/nova_gateway/core.py tests/test_nova_conversation_continuity_ledger.py
git commit -m "feat: preserve bounded conversation continuity"
```

---

### Task 5: 500-Case Conversation Evaluation Bank

**Files:**
- Create: `src/nova_conversation_eval.py`
- Create: `tools/generate_nova_conversation_eval_pack.py`
- Create: `data/evals/nova_conversation_variations_v1.json`
- Create: `tests/test_nova_conversation_eval.py`
- Modify: `src/nova_adversarial_eval.py`
- Modify: `nova_enhanced_server.py` health/config diagnostics

**Interfaces:**
- Consumes: shared conversation decision and optional managed-chat callable.
- Produces: `ConversationEvalCase`, `ConversationEvalReport`,
  `load_conversation_eval_pack(path)`, and `run_conversation_eval(cases, chat=None)`.

- [ ] **Step 1: Write failing pack and evaluation tests**

```python
from nova_conversation_eval import load_conversation_eval_pack, run_conversation_eval


def test_versioned_pack_contains_at_least_five_hundred_unique_cases():
    cases = load_conversation_eval_pack("data/evals/nova_conversation_variations_v1.json")
    assert len(cases) >= 500
    assert len({case.case_id for case in cases}) == len(cases)
    assert {"social", "relationship", "followup", "current_fact", "recovery"} <= {
        case.category for case in cases
    }


def test_decision_eval_reports_exact_failures_without_training_writes():
    cases = load_conversation_eval_pack("data/evals/nova_conversation_variations_v1.json")
    report = run_conversation_eval(cases[:25])
    assert report.total == 25
    assert report.failed == 0
    assert report.training_writes == 0
    assert report.content_logged is False
```

- [ ] **Step 2: Run tests and observe missing module/data failures**

```powershell
py -3.11 -m pytest -q tests/test_nova_conversation_eval.py
```

Expected: collection fails because the module and pack do not exist.

- [ ] **Step 3: Implement schema, deterministic generator, and runner**

Use this public case shape:

```python
@dataclass(frozen=True)
class ConversationEvalCase:
    case_id: str
    category: str
    prompt: str
    expected_intent_family: str
    required_signals: tuple[str, ...]
    prohibited_signals: tuple[str, ...]


@dataclass(frozen=True)
class ConversationEvalReport:
    version: str
    total: int
    passed: int
    failed: int
    category_scores: dict[str, float]
    failures: tuple[dict[str, str], ...]
    latency_ms: float
    training_writes: int = 0
    content_logged: bool = False
```

The generator combines reviewed literal seed phrases with bounded spelling,
punctuation, contraction, shorthand, and speech-to-text transforms. Deduplicate
by canonical prompt plus expected family. Include explicit negative cases such
as `Did the mayor miss the meeting?` so relationship matching cannot swallow
factual questions. Generate at least 520 unique cases to leave margin above the
500-case acceptance floor.

Run the generator:

```powershell
py -3.11 tools/generate_nova_conversation_eval_pack.py
```

The runner calls `understand_conversation_turn`, measures safe metadata, and
never calls training or memory writers. Add a bounded optional full-chat mode
used only by explicit evaluation commands.

- [ ] **Step 4: Run pack, adversarial, and training-pollution tests**

```powershell
py -3.11 -m pytest -q tests/test_nova_conversation_eval.py tests/test_nova_adversarial_eval.py tests/test_nova_training_studio.py tests/test_nova_enhanced_server.py
```

Expected: all selected tests pass and no evaluation prompts appear in
`data/conversation_training_data.jsonl`.

- [ ] **Step 5: Restart and live-fit Task 5**

Run the complete decision bank, then a representative 100-case full-chat bank
through local `/api/chat` with memory and training writes disabled. Save the
machine-readable report under `reports/` and fix every deterministic failure
before continuing.

- [ ] **Step 6: Commit only Task 5 files**

```powershell
git add -- src/nova_conversation_eval.py src/nova_adversarial_eval.py tools/generate_nova_conversation_eval_pack.py data/evals/nova_conversation_variations_v1.json tests/test_nova_conversation_eval.py nova_enhanced_server.py
git commit -m "test: add 500-case Nova conversation evaluation"
```

---

### Task 6: Fused Vision and Safe Robot Navigation Snapshot

**Files:**
- Create: `src/nova_perception_fusion.py`
- Create: `tests/test_nova_perception_fusion.py`
- Modify: `nova_enhanced_server.py:_uploaded_picture_response`
- Modify: `src/nova_visual_perception.py`
- Modify: `src/nova_gateway/engines.py`
- Modify: `src/nova_tool_registry.py`

**Interfaces:**
- Consumes: Moondream semantic text/meta, OCR records, deterministic scene
  report, and sanitized browser sensor snapshot.
- Produces: `Observation`, `PerceptionSnapshot`, `fuse_perception(...)`, and
  `plan_safe_navigation(snapshot)`.

- [ ] **Step 1: Write failing fusion and safety tests**

```python
from nova_perception_fusion import fuse_perception, plan_safe_navigation


def test_fusion_separates_observed_inferred_and_unavailable_facts():
    snapshot = fuse_perception(
        semantic_text="A red chair is near a table.",
        semantic_meta={"used": True, "model": "moondream"},
        ocr_records=[{"text": "EXIT", "confidence": 0.94}],
        scene_report={"dominant_colors": ["red"], "navigation": {"metric_depth_available": False}},
        sensor_snapshot={},
    )
    assert snapshot.semantic_available is True
    assert snapshot.ocr_texts == ("EXIT",)
    assert snapshot.metric_depth_available is False
    assert "metric_distance" in snapshot.unavailable_capabilities


def test_single_camera_navigation_plan_never_authorizes_movement():
    snapshot = fuse_perception(
        semantic_text="An open hallway is visible.",
        semantic_meta={"used": True, "model": "moondream"},
        ocr_records=[],
        scene_report={"navigation": {"metric_depth_available": False}},
        sensor_snapshot={},
    )
    plan = plan_safe_navigation(snapshot)
    assert plan.movement_authorized is False
    assert "calibrated depth" in " ".join(plan.required_inputs).lower()
    assert plan.mode == "simulation_only"
```

- [ ] **Step 2: Run tests and observe missing-module failure**

```powershell
py -3.11 -m pytest -q tests/test_nova_perception_fusion.py
```

Expected: collection fails because `nova_perception_fusion` does not exist.

- [ ] **Step 3: Implement privacy-safe perception fusion**

```python
@dataclass(frozen=True)
class PerceptionSnapshot:
    semantic_available: bool
    semantic_model: str
    semantic_summary: str
    ocr_texts: tuple[str, ...]
    verified_scene_facts: tuple[str, ...]
    object_observations: tuple[str, ...]
    metric_depth_available: bool
    sensor_channels: tuple[str, ...]
    unavailable_capabilities: tuple[str, ...]
    stale: bool
    schema_version: str = "1.0"

    def safe_trace(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "semantic_available": self.semantic_available,
            "semantic_model": self.semantic_model,
            "ocr_count": len(self.ocr_texts),
            "verified_scene_fact_count": len(self.verified_scene_facts),
            "object_observation_count": len(self.object_observations),
            "metric_depth_available": self.metric_depth_available,
            "sensor_channels": list(self.sensor_channels),
            "unavailable_capabilities": list(self.unavailable_capabilities),
            "stale": self.stale,
            "image_content_logged": False,
            "sensor_values_logged": False,
        }


@dataclass(frozen=True)
class NavigationPlan:
    mode: str
    movement_authorized: bool
    hazards: tuple[str, ...]
    unknowns: tuple[str, ...]
    required_inputs: tuple[str, ...]
    suggested_observation: str
```

Parse object observations conservatively from bounded Moondream noun phrases;
mark them inferred unless an external structured detector is configured.
Depth is available only when sanitized sensor metadata declares a calibrated
depth/LiDAR channel with a fresh timestamp. Do not persist image bytes, OCR
content, semantic text, or sensor values in safe traces.

Attach `perception_fusion` safe trace to uploaded-picture responses. Register
read-only `vision.observe` and `robot.observe` tool metadata. Keep
`robot.move` disabled and permission-gated.

- [ ] **Step 4: Run vision, OCR, tools, and robot-policy tests**

```powershell
py -3.11 -m pytest -q tests/test_nova_perception_fusion.py tests/test_nova_visual_perception.py tests/test_nova_ocr.py tests/test_nova_tool_registry.py tests/test_nova_action_policy.py tests/test_nova_enhanced_server.py
```

Expected: all selected tests pass and no single-image case authorizes movement.

- [ ] **Step 5: Restart and live-fit Task 6**

Upload a controlled picture containing multiple objects and text, then test a
live camera frame. Verify semantic answer, OCR, structured observations,
unavailable metric depth, and simulation-only navigation. Verify no image or
sensor content is written to safe logs.

- [ ] **Step 6: Commit only Task 6 files**

```powershell
git add -- src/nova_perception_fusion.py src/nova_visual_perception.py src/nova_gateway/engines.py src/nova_tool_registry.py nova_enhanced_server.py tests/test_nova_perception_fusion.py
git commit -m "feat: fuse Nova vision observations safely"
```

---

### Task 7: Stable Answer-Status UI

**Files:**
- Modify: `nova_chat_web.html`
- Modify: `nova_enhanced_server.py` trace/status projection
- Create: `tests/test_nova_answer_status_ui.py`

**Interfaces:**
- Consumes: privacy-safe fields from conversation decision, response repair,
  model escalation, context, verification, grounding, and perception traces.
- Produces: `answer_status` response metadata and a fixed-height,
  horizontally-safe status UI with collapsible details.

- [ ] **Step 1: Write failing response-projection and HTML behavior tests**

```python
def test_answer_status_projection_contains_only_safe_operational_fields():
    status = server._answer_status_from_trace({
        "conversation_decision": {"intent_family": "relationship"},
        "model": "qwen2.5:1.5b",
        "response_repair": {"repaired": True, "reason": "reviewed_intent_repair"},
        "answer_firewall": {"status": "passed"},
        "memory_v2_retrieved": 2,
    })
    assert status == {
        "intent": "relationship",
        "model": "qwen2.5:1.5b",
        "memory": "2 recalled",
        "repair": "repaired",
        "safety": "passed",
        "vision": "not used",
    }
    assert "prompt" not in status
    assert "reasoning" not in status


def test_mobile_status_row_is_fixed_height_and_details_are_collapsible():
    html = server.WEB_HTML
    assert 'class="answer-status-row"' in html
    assert 'class="answer-status-details"' in html
    assert 'aria-expanded="false"' in html
    assert "overflow-x: auto" in html
    assert "min-height:" in html
```

- [ ] **Step 2: Run tests and observe missing projection/UI failures**

```powershell
py -3.11 -m pytest -q tests/test_nova_answer_status_ui.py
```

Expected: failures for missing `_answer_status_from_trace` and status markup.

- [ ] **Step 3: Implement safe status projection and stable UI**

Add `_answer_status_from_trace(trace)` with allowlisted values only. Attach it
to `/api/chat` responses as an optional backward-compatible `answer_status`
field.

Add fixed-height status markup generated from text nodes, never `innerHTML`:

```javascript
function buildAnswerStatus(status) {
  const row = document.createElement("div");
  row.className = "answer-status-row";
  const labels = [
    ["Brain", status.model || "Nova"],
    ["Intent", status.intent || "conversation"],
    ["Memory", status.memory || "not used"],
    ["Safety", status.safety || "checked"]
  ];
  labels.forEach(([name, value]) => {
    const chip = document.createElement("span");
    chip.className = "answer-status-chip";
    chip.textContent = `${name}: ${value}`;
    row.appendChild(chip);
  });
  return row;
}
```

Use:

```css
.answer-status-row {
  display: flex;
  gap: 6px;
  min-height: 30px;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
  overscroll-behavior-x: contain;
}
.answer-status-chip {
  flex: 0 0 auto;
  white-space: nowrap;
}
.answer-status-details[hidden] {
  display: none;
}
```

Keep autoscroll conditional on the user being near the bottom. Preserve both
existing horizontally scrollable bottom control rails and their event handlers.

- [ ] **Step 4: Run UI, server, mobile-scroll, and security tests**

```powershell
py -3.11 -m pytest -q tests/test_nova_answer_status_ui.py tests/test_nova_enhanced_server.py tests/test_nova_desktop_experience.py tests/test_nova_gateway_security.py
```

Expected: all selected tests pass and existing bottom-button selectors remain
present.

- [ ] **Step 5: Restart and live-fit Task 7**

Use the in-app browser at desktop and narrow mobile widths. Send normal,
repaired, escalated, memory, and vision turns. Verify chips, collapsible
details, no prompt/private data, stable message height, retained scroll
position, horizontal bottom controls, and clickable camera/mic/model buttons.

- [ ] **Step 6: Commit only Task 7 files**

```powershell
git add -- nova_chat_web.html nova_enhanced_server.py tests/test_nova_answer_status_ui.py
git commit -m "feat: show stable privacy-safe Nova answer status"
```

---

### Task 8: Final Configuration, Documentation, and Complete Live Audit

**Files:**
- Modify: `nova_llm_config.json`
- Modify: `.nova_llm_config`
- Modify: `docs/NOVA_COGNITIVE_OPERATING_LAYER.md`
- Create: `reports/NOVA_CONVERSATION_INTELLIGENCE_UPGRADE.md`
- Create: `reports/nova_conversation_eval_v1.json`
- Modify: `reports/NOVA_COGNITIVE_UPGRADE_AUDIT.md`

**Interfaces:**
- Consumes: all seven completed task interfaces and reports.
- Produces: safe feature flags, runbook, compatibility report, machine-readable
  evaluation, and final audit.

- [ ] **Step 1: Add failing configuration compatibility tests**

```python
def test_new_flags_default_safe_and_raw_adapters_remain_independent():
    config = server._runtime_cognitive_config()
    assert config["conversation_intelligence"]["enabled"] is True
    assert config["response_repair"]["maximum_attempts"] == 1
    assert config["model_routing"]["middle_model"] == "qwen2.5:3b"
    assert config["robot"]["physical_movement_enabled"] is False
    assert config["raw_adapters"]["managed_interception"] is False
```

- [ ] **Step 2: Run the configuration test and observe missing fields**

```powershell
py -3.11 -m pytest -q tests/test_nova_enhanced_server.py -k "new_flags_default_safe"
```

Expected: failure because the new configuration projection is incomplete.

- [ ] **Step 3: Add exact safe defaults and documentation**

Merge these fields through the existing configuration loader:

```json
{
  "conversation_intelligence": {
    "enabled": true,
    "schema_version": "1.0"
  },
  "response_repair": {
    "enabled": true,
    "maximum_attempts": 1
  },
  "model_routing": {
    "small_model": "qwen2.5:1.5b",
    "middle_model": "qwen2.5:3b",
    "deep_models_require_resource_approval": true
  },
  "conversation_continuity": {
    "enabled": true,
    "maximum_open_loops": 8
  },
  "perception": {
    "fusion_enabled": true,
    "require_calibrated_depth_for_navigation": true
  },
  "robot": {
    "simulation_enabled": true,
    "physical_movement_enabled": false
  },
  "telemetry": {
    "enabled": false,
    "log_prompts": false,
    "log_private_memory": false
  },
  "raw_adapters": {
    "managed_interception": false
  }
}
```

Document startup, rollback flags, status chips, model tiers, continuity privacy,
evaluation commands, perception limitations, and simulation-only robot policy.

- [ ] **Step 4: Run every focused suite and the 500-case evaluator**

```powershell
py -3.11 -m pytest -q tests/test_nova_conversation_intelligence.py tests/test_nova_response_repair.py tests/test_nova_model_escalation_policy.py tests/test_nova_conversation_continuity_ledger.py tests/test_nova_conversation_eval.py tests/test_nova_perception_fusion.py tests/test_nova_answer_status_ui.py
py -3.11 -m nova_conversation_eval --pack data/evals/nova_conversation_variations_v1.json --report reports/nova_conversation_eval_v1.json
```

Expected: focused tests pass, at least 500 unique cases run, zero deterministic
classification failures, and zero training writes.

- [ ] **Step 5: Run the complete existing and new test suite**

```powershell
py -3.11 -m pytest -q
```

Expected: zero failures. Skips must remain explained by existing optional
hardware/provider availability.

- [ ] **Step 6: Perform the final live audit**

Restart Nova and validate:

- twenty natural/slang/relationship turns
- ten follow-up and topic-continuity turns across two clients
- five strict current-fact/evidence boundaries
- small, middle, and denied-deep model routes
- raw Qwen and raw Dolphin untouched outputs
- picture upload, OCR, perception fusion, and simulation-only navigation
- answer-status chips and bottom-control interaction at mobile width
- `/health`, `/nova/v1/health`, `/v1/models`, and `/v1/chat/completions`

Record only safe metadata and counts in
`reports/NOVA_CONVERSATION_INTELLIGENCE_UPGRADE.md`.

- [ ] **Step 7: Commit only Task 8 files**

```powershell
git add -- nova_llm_config.json .nova_llm_config docs/NOVA_COGNITIVE_OPERATING_LAYER.md reports/NOVA_CONVERSATION_INTELLIGENCE_UPGRADE.md reports/nova_conversation_eval_v1.json reports/NOVA_COGNITIVE_UPGRADE_AUDIT.md tests/test_nova_enhanced_server.py
git commit -m "docs: audit Nova conversation intelligence upgrade"
```

