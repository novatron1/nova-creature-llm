from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import nova_enhanced_server as server  # noqa: E402
from nova_answer_firewall import evaluate_answer  # noqa: E402
from nova_cognitive_os import route  # noqa: E402
from nova_conversation_intelligence import understand_conversation_turn  # noqa: E402
from nova_response_repair import (  # noqa: E402
    repair_rejected_response,
    reviewed_direct_response,
)
import pytest  # noqa: E402


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
    firewall = evaluate_answer(
        prompt,
        rejected,
        trace={"domain": "general_conversation"},
    )

    result = repair_rejected_response(prompt, rejected, decision, firewall)

    assert firewall.accepted is False
    assert result.repaired is True
    assert result.attempt_count == 1
    assert "day" in result.answer.lower()
    assert result.safe_trace()["content_logged"] is False


def test_practical_support_repair_uses_the_reviewed_money_need_answer():
    prompt = "I need some money"
    decision = understand_conversation_turn(prompt)
    rejected = "I'm here with you. Tell me what you want to do next."
    firewall = evaluate_answer(prompt, rejected, trace={"domain": "general_conversation"})

    result = repair_rejected_response(prompt, rejected, decision, firewall)

    assert firewall.accepted is False
    assert result.repaired is True
    assert result.answer == (
        "I hear you. Is this urgent for rent, food, or bills, or are you trying "
        "to increase your income? Tell me the amount and deadline, and I’ll help "
        "you make a realistic plan."
    )


def test_managed_server_preserves_a_relevant_small_model_practical_support_answer(
    monkeypatch,
):
    accepted = "Let's start with the rent amount due tomorrow and your available income."
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            accepted,
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["speech_output_transformer"],
                "skills": [],
                "route_path": ["cognitive_os"],
                "confidence": 0.8,
                "local_llm_synthesis_used": True,
            },
        ),
    )

    answer, trace = server._run_nova_chat_turn(
        "I need some money",
        context={
            "nova_gateway": True,
            "private_mode": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert answer == accepted
    assert trace["conversation_decision"]["intent_family"] == "practical_support"
    assert trace.get("response_repair", {}).get("repaired") is not True


def test_managed_server_repairs_off_topic_practical_support_draft_as_safe(monkeypatch):
    rejected = "I'm here with you. Tell me what you want to do next."
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            rejected,
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["speech_output_transformer"],
                "skills": [],
                "route_path": ["cognitive_os"],
                "confidence": 0.4,
                "local_llm_synthesis_used": True,
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_candidate_retry_allowed",
        lambda trace, context: (_ for _ in ()).throw(
            AssertionError("reviewed repair should run before model escalation")
        ),
    )

    answer, trace = server._run_nova_chat_turn(
        "I need some money",
        context={
            "nova_gateway": True,
            "private_mode": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert answer.startswith("I hear you.")
    assert trace["response_repair"]["repaired"] is True
    assert trace["answer_firewall"]["status"] == "passed_after_repair"


def test_current_fact_repair_never_invents_evidence():
    prompt = "Who is the current mayor of Example City?"
    decision = understand_conversation_turn(prompt)
    rejected = "Jane Example is mayor."
    firewall = evaluate_answer(
        prompt,
        rejected,
        trace={"domain": "current_facts"},
    )

    result = repair_rejected_response(prompt, rejected, decision, firewall)

    assert result.repaired is False
    assert result.reason == "strict_evidence_required"
    assert result.attempt_count == 0
    assert result.answer == rejected


def test_unknown_open_ended_turn_is_not_replaced_by_a_canned_social_answer():
    prompt = "Imagine a new kind of city."
    decision = understand_conversation_turn(prompt)
    rejected = "I'm here with you. Tell me what you want to do next."
    firewall = evaluate_answer(prompt, rejected)

    result = repair_rejected_response(prompt, rejected, decision, firewall)

    assert result.repaired is False
    assert result.reason == "no_deterministic_repair"


@pytest.mark.parametrize(
    ("prompt", "subtype", "answer_fragment"),
    (
        ("How's ur day going?", "day_checkin", "day"),
        ("What u doing right now?", "activity_checkin", "working"),
        ("What's on your mind?", "mind_checkin", "mind"),
        ("Hey", "greeting", "hey"),
        ("Do you love me?", "affection_checkin", "care"),
        ("What do I mean to you?", "relationship_meaning", "connection"),
    ),
)
def test_reviewed_social_subtypes_keep_their_meaning(
    prompt,
    subtype,
    answer_fragment,
):
    decision = understand_conversation_turn(prompt)

    answer = reviewed_direct_response(decision)

    assert decision.intent_subtype == subtype
    assert answer_fragment in answer.lower()


def test_cognitive_fast_path_consumes_shared_reviewed_relationship_answer():
    prompt = "Were you thinking about me?"
    decision = understand_conversation_turn(prompt)

    answer, trace = route(
        prompt,
        context={
            "conversation_decision": decision,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert "connection" in answer.lower()
    assert "human" in answer.lower()
    assert trace["final_answer_source"] == "reviewed_conversation_response"


def test_managed_server_repairs_social_fallback_before_model_escalation(monkeypatch):
    rejected = "I'm here with you. Tell me what you want to do next."
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            rejected,
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["speech_output_transformer"],
                "skills": [],
                "route_path": ["cognitive_os"],
                "confidence": 0.4,
                "local_llm_synthesis_used": False,
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_candidate_retry_allowed",
        lambda trace, context: (_ for _ in ()).throw(
            AssertionError("reviewed repair should run before model escalation")
        ),
    )

    answer, trace = server._run_nova_chat_turn(
        "How has your day been?",
        context={
            "nova_gateway": True,
            "private_mode": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert "day" in answer.lower()
    assert trace["response_repair"]["repaired"] is True
    assert trace["response_repair"]["attempt_count"] == 1
    assert trace["final_answer_source"] == "reviewed_response_repair"


def test_managed_server_keeps_emotional_today_checkin_out_of_post_grounding(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "I'm steady and focused, and I'm glad we're talking.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["speech_output_transformer"],
                "skills": [],
                "route_path": ["cognitive_os"],
                "confidence": 0.9,
                "local_llm_synthesis_used": False,
            },
        ),
    )

    answer, trace = server._run_nova_chat_turn(
        "How are you feeling about us today?",
        context={
            "nova_gateway": True,
            "private_mode": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert "steady" in answer.lower()
    assert trace["fact_grounding"]["status"] == "not_required"
    assert trace["source"] != "fact_grounding_guard"


@pytest.mark.parametrize(
    "prompt",
    (
        "Do you care about me?",
        "What does our connection mean?",
        "I am feeling nervous today",
        "I had a rough day",
        "I am proud of myself",
        "I feel better now",
        "I need some encouragement",
        "Can we talk for a minute?",
        "Thanks for being here",
        "You are funny",
        "That made me laugh",
        "What is on your mind?",
        "I appreciate you",
        "Good night Nova",
    ),
)
def test_live_audit_natural_turns_have_reviewed_direct_responses(prompt):
    decision = understand_conversation_turn(prompt)

    answer = reviewed_direct_response(decision)

    assert answer


def test_managed_server_uses_reviewed_natural_answer_before_slow_model(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("reviewed natural turns must not wait on the CPU model")
        ),
    )

    answer, trace = server._run_nova_chat_turn(
        "I am feeling nervous today",
        context={
            "evaluation_only": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
            "conversation_summary_write_allowed": False,
        },
    )

    assert "one piece at a time" in answer.lower()
    assert trace["final_answer_source"] == "reviewed_conversation_response"
    assert trace["local_llm_synthesis_used"] is False


def test_managed_slang_greeting_does_not_wait_for_cpu_model(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("a recognized greeting must stay deterministic")
        ),
    )

    answer, trace = server._run_nova_chat_turn(
        "Yo, what is up?",
        context={
            "evaluation_only": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
            "conversation_summary_write_allowed": False,
        },
    )

    assert "here" in answer.lower()
    assert trace["final_answer_source"] == "reviewed_conversation_response"
    assert trace["local_llm_synthesis_used"] is False
