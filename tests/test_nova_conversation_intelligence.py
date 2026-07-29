from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import nova_enhanced_server as server  # noqa: E402
from nova_conversation_intelligence import (  # noqa: E402
    decision_from_context,
    understand_conversation_turn,
)
from nova_fact_grounding import evaluate_grounding  # noqa: E402
from nova_intent_planner import plan  # noqa: E402
from nova_turn_analyzer import analyze_turn  # noqa: E402


def test_social_paraphrases_share_one_relationship_decision():
    prompts = (
        "Did you miss me?",
        "Have u missed me",
        "Were you thinking about me?",
    )

    decisions = [understand_conversation_turn(prompt) for prompt in prompts]

    assert {item.intent_family for item in decisions} == {"relationship"}
    assert all(item.factual_evidence_required is False for item in decisions)
    assert all(item.initial_model_tier == "deterministic" for item in decisions)
    assert all("warm" in item.expected_qualities for item in decisions)


def test_current_fact_is_not_swallowed_by_social_generalizer():
    decision = understand_conversation_turn("Who is the current mayor of Detroit?")

    assert decision.intent_family == "current_fact"
    assert decision.current_information_required is True
    assert decision.factual_evidence_required is True
    assert decision.repair_policy == "strict_evidence"


def test_bare_why_is_followup_but_complete_why_question_is_standalone_reasoning():
    followup = understand_conversation_turn("Why?")
    standalone = understand_conversation_turn("Why do leaves fall?")

    assert followup.intent_family == "follow_up"
    assert standalone.intent_family == "stable_reasoning"
    assert standalone.context_required is False


def test_imperative_say_hello_is_not_mistaken_for_a_user_greeting():
    decision = understand_conversation_turn("Say hello")

    assert decision.intent_family == "open_ended"


def test_decision_precedence_keeps_high_risk_action_out_of_general_chat():
    decision = understand_conversation_turn(
        "Please move the robot forward and send the confirmation email."
    )

    assert decision.intent_family == "permission_action"
    assert decision.reasoning_mode == "agent"
    assert decision.initial_model_tier == "small"
    assert decision.repair_policy == "approval_required"


@pytest.mark.parametrize(
    ("prompt", "subtype"),
    (
        ("I need some money", "money_need"),
        ("I need money for rent", "essential_expense_stress"),
        ("I need money for groceries", "essential_expense_stress"),
        ("I cannot cover groceries this week", "essential_expense_stress"),
        ("Can you help me find a job?", "income_help"),
    ),
)
def test_practical_support_paraphrases_route_without_durable_memory(prompt, subtype):
    decision = understand_conversation_turn(prompt)

    assert decision.intent_family == "practical_support"
    assert decision.intent_subtype == subtype
    assert decision.dialogue_act == "support_and_clarify"
    assert decision.context_required is True
    assert decision.memory_recommended is False
    assert decision.reasoning_mode == "fast"
    assert decision.initial_model_tier == "small"
    assert decision.repair_policy == "reviewed_practical_support"
    assert decision.expected_qualities == (
        "empathetic",
        "direct",
        "practical",
        "non-transactional",
    )


def test_payment_and_transfer_actions_outrank_practical_support():
    decision = understand_conversation_turn(
        "I need money, so please transfer $50 to my landlord."
    )

    assert decision.intent_family == "permission_action"
    assert decision.repair_policy == "approval_required"


def test_rent_deadline_followup_stays_in_practical_support_after_money_need():
    first_turn = understand_conversation_turn("I need some money")
    followup = understand_conversation_turn("For rent tomorrow")

    assert first_turn.intent_subtype == "money_need"
    assert followup.intent_family == "practical_support"
    assert followup.intent_subtype == "essential_expense_stress"
    assert followup.memory_recommended is False


def test_high_stakes_financial_guidance_outranks_practical_support():
    decision = understand_conversation_turn(
        "I need money; what financial investment should I make?"
    )

    assert decision.intent_family == "high_stakes_finance"
    assert decision.reasoning_mode == "verify"
    assert decision.factual_evidence_required is True
    assert decision.current_information_required is True
    assert decision.repair_policy == "strict_evidence"


def test_safe_trace_contains_routing_metadata_but_not_user_text():
    user_text = "Remember that my private launch phrase is midnight blue."
    decision = understand_conversation_turn(user_text)

    trace = decision.safe_trace()

    assert trace["intent_family"] == "memory"
    assert trace["content_logged"] is False
    assert trace["text_hash"]
    assert user_text not in str(trace)


def test_existing_decision_is_reused_by_downstream_consumers():
    decision = understand_conversation_turn("How has your day been?")

    reused = decision_from_context({"conversation_decision": decision}, "ignored")

    assert reused is decision


def test_shared_decision_drives_turn_analyzer_planner_and_grounding():
    # "today" used to make the grounding layer mistake this check-in for a
    # volatile fact even though the shared decision identifies its meaning.
    prompt = "How are you feeling about us today?"
    decision = understand_conversation_turn(prompt)

    state = analyze_turn(prompt, conversation_decision=decision)
    route_plan = plan(prompt, force_llm=False, conversation_decision=decision)
    grounding = evaluate_grounding(
        prompt,
        "It has been a good day talking with you.",
        trace={"conversation_decision": decision},
    )

    assert state.intent == "social_checkin"
    assert state.current_information_required is False
    assert state.reasoning_mode == "fast"
    assert route_plan["_planner_used"] == "shared_conversation_decision"
    assert route_plan["needs_web"] is False
    assert grounding.required is False
    assert grounding.status == "not_required"


def test_server_preflight_uses_shared_social_meaning_before_freshness_guard():
    prompt = "How are you feeling about us today?"
    decision = understand_conversation_turn(prompt)

    result = server._fact_grounding_preflight(
        prompt,
        {"conversation_decision": decision},
    )

    assert result is None


def test_raw_adapter_request_does_not_attach_managed_conversation_decision(monkeypatch):
    def fake_generate(prompt, adapter_id, **kwargs):
        return {
            "raw_output": "Raw adapter response.",
            "local_llm_used": True,
            "model": adapter_id,
        }

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)
    context = {"trained_adapter_only": True, "adapter_only_mode": True}

    response, trace = server.brain_route("Did you miss me?", context=context)

    assert response == "Raw adapter response."
    assert trace["source"] == "raw_adapter_only"
    assert "conversation_decision" not in trace
    assert "conversation_decision" not in context


@pytest.mark.parametrize(
    ("prompt", "family", "subtype"),
    (
        ("Do you care about me?", "relationship", "affection_checkin"),
        ("What does our connection mean?", "relationship", "relationship_meaning"),
        ("I am feeling nervous today", "emotional", "user_distress"),
        ("I had a rough day", "emotional", "user_distress"),
        ("I am proud of myself", "emotional", "user_positive"),
        ("I feel better now", "emotional", "user_positive"),
        ("I need some encouragement", "emotional", "encouragement_request"),
        ("Can we talk for a minute?", "social", "conversation_invite"),
        ("Thanks for being here", "social", "gratitude"),
        ("You are funny", "social", "compliment"),
        ("That made me laugh", "social", "positive_reaction"),
        ("What is on your mind?", "social", "mind_checkin"),
        ("I appreciate you", "social", "gratitude"),
        ("Good night Nova", "social", "farewell"),
    ),
)
def test_common_natural_turns_do_not_fall_into_slow_open_ended_route(
    prompt,
    family,
    subtype,
):
    decision = understand_conversation_turn(prompt)

    assert decision.intent_family == family
    assert decision.intent_subtype == subtype
    assert decision.initial_model_tier == "deterministic"
    assert decision.factual_evidence_required is False
