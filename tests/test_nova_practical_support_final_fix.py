from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import nova_cognitive_os as cognitive_os  # noqa: E402
import nova_enhanced_server as server  # noqa: E402
from nova_conversation_context import bounded_conversation_history  # noqa: E402
from nova_conversation_intelligence import understand_conversation_turn  # noqa: E402


def _install_cognitive_synthesizer(monkeypatch, responses):
    generated = []
    response_iter = iter(responses)

    class AnswerSynthesizer:
        @staticmethod
        def try_direct_answer(*_args):
            return None, False

        @staticmethod
        def anti_echo_check(_answer):
            return True

    class ContextBuilder:
        @staticmethod
        def build(message, plan, **_kwargs):
            return {
                "user_question": message,
                "route": plan["route"],
                "system_prompt": "Answer as Nova.",
            }

    class Synthesizer:
        LAST_LOCAL_LLM_MODEL = "qwen2.5:1.5b"

        @staticmethod
        def generate(packet):
            generated.append(dict(packet))
            return next(response_iter), True, None

    natural_chat = SimpleNamespace(
        build_conversation_state=lambda _message: None,
        get_recent_memory=lambda: [],
        natural_chat_enabled=lambda: True,
        shape_response=lambda response, **_kwargs: response,
        shape_verified_response=lambda response, **_kwargs: response,
        update_conversation_memory=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "nova_natural_chat", natural_chat)
    monkeypatch.setattr(cognitive_os, "_get_ltm", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_slot_retrieval", lambda: None)
    monkeypatch.setattr(
        cognitive_os,
        "_get_answer_synthesizer",
        lambda: AnswerSynthesizer(),
    )
    monkeypatch.setattr(
        cognitive_os,
        "_get_context_builder",
        lambda: ContextBuilder(),
    )
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: Synthesizer())
    monkeypatch.setattr(cognitive_os, "_get_web", lambda: None)
    monkeypatch.setattr(cognitive_os, "_reviewed_conversation_answer", lambda _text: None)
    monkeypatch.setattr(cognitive_os, "_log_training", lambda *_args, **_kwargs: None)
    return generated


def _managed_context(**overrides):
    context = {
        "nova_gateway": True,
        "memory_read_allowed": False,
        "memory_write_allowed": False,
        "conversation_memory_allowed": False,
        "conversation_summary_write_allowed": True,
    }
    context.update(overrides)
    return context


def test_practical_support_cognitive_route_gives_small_qwen_first_chance(monkeypatch):
    accepted = (
        "Let's start with the amount you need and when it is due, then we can "
        "make a realistic plan."
    )
    generated = _install_cognitive_synthesizer(monkeypatch, [accepted])
    decision = understand_conversation_turn("I need some money")

    answer, trace = cognitive_os.route(
        "I need some money",
        context={
            "conversation_decision": decision,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert len(generated) == 1
    assert answer == accepted
    assert trace["local_llm_synthesis_used"] is True
    assert trace["local_llm_model"] == "qwen2.5:1.5b"
    assert "fast_general_response" not in trace["skills"]


@pytest.mark.parametrize(
    ("draft", "expected_repaired"),
    (
        (
            "Let's start with the amount you need and when it is due, then we "
            "can make a realistic plan.",
            False,
        ),
        ("I'm here with you. Tell me what you want to do next.", True),
    ),
)
def test_managed_cognitive_route_repairs_only_rejected_small_qwen_drafts(
    monkeypatch,
    draft,
    expected_repaired,
):
    generated = _install_cognitive_synthesizer(monkeypatch, [draft])
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: cognitive_os.route(text, context=context),
    )
    if expected_repaired:
        monkeypatch.setattr(
            server,
            "_candidate_retry_allowed",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("reviewed repair must run before model escalation")
            ),
        )

    answer, trace = server._run_nova_chat_turn(
        "I need some money",
        context=_managed_context(),
    )

    assert len(generated) == 1
    assert trace["conversation_decision"]["intent_family"] == "practical_support"
    assert trace.get("response_repair", {}).get("repaired", False) is expected_repaired
    if expected_repaired:
        assert answer.startswith("I hear you.")
        assert trace["answer_firewall"]["status"] == "passed_after_repair"
    else:
        assert answer == draft


@pytest.mark.parametrize(
    "prompt",
    (
        "Is crypto a good idea for my savings?",
        "Are stocks worth it right now?",
        "Would investing in an index fund be a good idea?",
        "Could I invest in crypto for a house deposit?",
        "Is this tax strategy worth it?",
        "Would this insurance policy be a good idea?",
        "Could consolidating my credit be worth it?",
        "Are adjustable-rate mortgages a good idea?",
    ),
)
def test_natural_finance_advice_outranks_practical_support(prompt):
    decision = understand_conversation_turn(prompt)

    assert decision.intent_family == "high_stakes_finance"
    assert decision.intent_subtype == "financial_guidance"
    assert decision.reasoning_mode == "verify"
    assert decision.factual_evidence_required is True
    assert decision.current_information_required is True


@pytest.mark.parametrize(
    "prompt",
    (
        "I need some money",
        "I cannot pay rent tomorrow",
        "I am behind on rent",
        "I do not have enough for groceries",
        "Can you help me budget for groceries this week?",
        "I lost my job and need income",
    ),
)
def test_hardship_and_budgeting_support_do_not_become_finance_advice(prompt):
    decision = understand_conversation_turn(prompt)

    assert decision.intent_family == "practical_support"
    assert decision.memory_recommended is False


@pytest.mark.parametrize(
    "prompt",
    (
        "Pay my rent tomorrow.",
        "Please buy groceries for me.",
        "Transfer $50 to my landlord.",
        "Send my landlord the rent money.",
        "Can you pay my electric bill?",
        "Will you buy food for me?",
        "Could you transfer money to my bank account?",
        "Would you send $20 to my landlord?",
    ),
)
def test_nova_directed_transactions_remain_permission_actions(prompt):
    decision = understand_conversation_turn(prompt)

    assert decision.intent_family == "permission_action"
    assert decision.repair_policy == "approval_required"


@pytest.mark.parametrize(
    ("prompt", "subtype"),
    (
        ("I cannot pay rent tomorrow", "essential_expense_stress"),
        ("I am behind on rent", "essential_expense_stress"),
        ("I do not have enough for groceries", "essential_expense_stress"),
        ("I need help finding work", "income_help"),
        ("I lost my job and need income", "income_help"),
    ),
)
def test_hardship_descriptions_are_practical_support(prompt, subtype):
    decision = understand_conversation_turn(prompt)

    assert decision.intent_family == "practical_support"
    assert decision.intent_subtype == subtype
    assert decision.memory_recommended is False


@pytest.mark.parametrize(
    ("prompt", "subtype", "expected_fragment"),
    (
        (
            "I cannot pay rent tomorrow",
            "essential_expense_stress",
            "what amount are you short",
        ),
        (
            "I lost my job and need income",
            "income_help",
            "what kind of work can you do",
        ),
    ),
)
def test_practical_support_subtype_repairs_pass_the_managed_firewall(
    monkeypatch,
    prompt,
    subtype,
    expected_fragment,
):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (
            "I'm here with you. Tell me what you want to do next.",
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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("reviewed repair must run before model escalation")
        ),
    )

    answer, trace = server._run_nova_chat_turn(prompt, context=_managed_context())

    assert trace["conversation_decision"]["intent_subtype"] == subtype
    assert expected_fragment in answer.lower()
    assert trace["response_repair"]["repaired"] is True
    assert trace["answer_firewall"]["status"] == "passed_after_repair"


def test_server_blocks_practical_support_rolling_summary_and_exports_safe_flag(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (
            "Let's identify the amount and deadline first.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["speech_output_transformer"],
                "skills": [],
                "route_path": ["cognitive_os"],
                "confidence": 0.9,
                "local_llm_synthesis_used": True,
            },
        ),
    )
    history = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"ordinary history {index}",
        }
        for index in range(8)
    ]

    _answer, trace = server._run_nova_chat_turn(
        "I need some money",
        context=_managed_context(
            conversation_history=history,
            conversation_summary={
                "schema_version": "1.0",
                "revision": 3,
                "topics": ["ordinary earlier topic"],
            },
        ),
    )

    assert trace["automatic_conversation_persistence_allowed"] is False
    assert "conversation_summary" not in trace
    assert "conversation_summary_updated" not in trace


def test_ordinary_chat_keeps_rolling_summary_and_safe_flag(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (
            "Here is a normal answer.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["speech_output_transformer"],
                "skills": [],
                "route_path": ["cognitive_os"],
                "confidence": 0.9,
            },
        ),
    )
    history = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"ordinary history {index}",
        }
        for index in range(8)
    ]

    _answer, trace = server._run_nova_chat_turn(
        "Tell me a joke",
        context=_managed_context(conversation_history=history),
    )

    assert trace["automatic_conversation_persistence_allowed"] is True
    assert trace["conversation_summary_updated"] is True


def test_two_turn_managed_practical_support_stays_focused_without_persistence(
    monkeypatch,
):
    observed_histories = []

    def focused_brain_route(text, context=None):
        history = bounded_conversation_history(context or {}, text)
        observed_histories.append(history)
        if text == "I need some money":
            return (
                "Is this urgent for rent, food, or bills?",
                {
                    "source": "cognitive_os",
                    "domain": "general_conversation",
                    "roles": ["speech_output_transformer"],
                    "skills": [],
                    "route_path": ["cognitive_os"],
                    "confidence": 0.9,
                    "local_llm_synthesis_used": True,
                },
            )
        assert history[-2:] == [
            {"role": "user", "content": "I need some money"},
            {
                "role": "assistant",
                "content": "Is this urgent for rent, food, or bills?",
            },
        ]
        return (
            "Let's focus on the rent due tomorrow and the amount you are short.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["memory_transformer", "speech_output_transformer"],
                "skills": ["context_recall"],
                "route_path": ["recent_conversation", "cognitive_os"],
                "confidence": 0.92,
                "local_llm_synthesis_used": True,
            },
        )

    monkeypatch.setattr(server, "brain_route", focused_brain_route)

    first_answer, first_trace = server._run_nova_chat_turn(
        "I need some money",
        context=_managed_context(),
    )
    second_answer, second_trace = server._run_nova_chat_turn(
        "For rent tomorrow",
        context=_managed_context(
            conversation_history=[
                {
                    "role": "user",
                    "content": "I need some money",
                    "ephemeral": True,
                },
                {
                    "role": "assistant",
                    "content": first_answer,
                    "ephemeral": True,
                },
            ],
            conversation_summary_history=[],
        ),
    )

    assert len(observed_histories) == 2
    assert "rent due tomorrow" in second_answer.lower()
    assert first_trace["automatic_conversation_persistence_allowed"] is False
    assert second_trace["automatic_conversation_persistence_allowed"] is False
    assert second_trace["conversation_decision"]["intent_subtype"] == (
        "essential_expense_stress"
    )
    assert "conversation_summary" not in first_trace
    assert "conversation_summary" not in second_trace
