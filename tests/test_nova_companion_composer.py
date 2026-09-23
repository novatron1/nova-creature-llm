from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


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
    from nova_companion.response_composer import compose_response
    from nova_companion.social_reasoning import plan_social_response

    state = CompanionState.new("user-a")
    intent = classify_social_intent("what is on your mind?")
    plan = plan_social_response(state, intent, [])
    result = compose_response(
        "what is on your mind?",
        "I'm here to help. How can I assist you today?",
        plan,
        trace={},
    )

    assert "assist you today" not in result.lower()
    assert result


def test_social_follow_up_replaces_generic_recovery_with_a_continuity_fallback():
    from nova_companion.intent import classify_social_intent
    from nova_companion.models import CompanionState
    from nova_companion.response_composer import compose_response
    from nova_companion.social_reasoning import plan_social_response

    state = CompanionState.new("user-a")
    intent = classify_social_intent("I am still thinking about the project we discussed")
    plan = plan_social_response(state, intent, [])
    result = compose_response(
        "I am still thinking about the project we discussed",
        "I caught an off-topic draft before sending it. The active Nova route did not produce a reliable answer, so I stopped it instead of pretending it was correct.",
        plan,
        trace={"source": "answer_firewall_recovery"},
    )
    assert "off-topic draft" not in result.lower()
    assert result


def test_social_fallback_trace_is_labeled_as_recovered_companion_answer():
    from nova_companion.intent import classify_social_intent
    from nova_companion.models import CompanionState
    from nova_companion.response_composer import compose_response
    from nova_companion.social_reasoning import plan_social_response

    state = CompanionState.new("user-a")
    intent = classify_social_intent("Give me one practical next step.")
    plan = plan_social_response(state, intent, [])
    trace = {
        "source": "answer_firewall_recovery",
        "final_answer_source": "answer_firewall_recovery",
        "answer_firewall": {
            "status": "blocked",
            "accepted": False,
            "intercepted": True,
            "reasons": ["generic_fallback_mismatch"],
        },
    }

    result = compose_response(
        "Give me one practical next step.",
        "I caught an off-topic draft before sending it. The active Nova route did not produce a reliable answer, so I stopped it instead of pretending it was correct.",
        plan,
        trace=trace,
    )

    assert result
    assert trace["source"] == "companion_continuity_fallback"
    assert trace["final_answer_source"] == "companion_continuity_fallback"
    assert trace["answer_firewall"]["status"] == "recovered_by_companion"
    assert trace["answer_firewall"]["accepted"] is True


def test_advice_recovery_has_a_small_actionable_fallback():
    from nova_companion.intent import classify_social_intent
    from nova_companion.models import CompanionState
    from nova_companion.response_composer import compose_response
    from nova_companion.social_reasoning import plan_social_response

    state = CompanionState.new("user-a")
    intent = classify_social_intent("Give me one practical next step.")
    plan = plan_social_response(state, intent, [])
    result = compose_response(
        "Give me one practical next step.",
        "I caught an off-topic draft before sending it. The active Nova route did not produce a reliable answer, so I stopped it instead of pretending it was correct.",
        plan,
        trace={"source": "answer_firewall_recovery"},
    )
    assert "off-topic draft" not in result.lower()
    assert "next step" in result.lower() or "write" in result.lower()


def test_social_plan_cannot_hide_a_rejected_technical_candidate():
    import copy
    from nova_companion.models import SocialPlan
    from nova_companion.response_composer import compose_response

    answer = "The active Nova route did not produce a reliable answer, so I stopped it instead of pretending it was correct."
    trace = {
        "source": "answer_firewall_recovery",
        "final_answer_source": "answer_firewall_recovery",
        "candidate_selection": {
            "selected": "recovery",
            "retry_result": "consistency_check_failed",
            "alternate_consistency": {"status": "blocked", "accepted": False},
        },
        "answer_firewall": {"status": "blocked", "accepted": False, "reasons": ["generic_fallback_mismatch"]},
    }
    original_trace = copy.deepcopy(trace)
    result = compose_response(
        "Compare local SQLite with a remote vector database for latency, offline use, and cost.",
        answer, SocialPlan.neutral(), trace=trace,
    )
    assert result == answer
    assert trace == original_trace


def test_social_recovery_preserves_failed_verification():
    from nova_companion.models import SocialPlan
    from nova_companion.response_composer import compose_response

    answer = "I stopped it instead of pretending it was correct."
    trace = {"source": "answer_firewall_recovery", "verification_v2": {"passed": False}}
    assert compose_response("Let's talk", answer, SocialPlan.neutral(), trace=trace) == answer
    assert trace["source"] == "answer_firewall_recovery"


def test_casual_companion_expression_is_animated_and_curious():
    from nova_companion.intent import classify_social_intent
    from nova_companion.models import CompanionState, MoodState
    from nova_companion.personality import expression_modifiers

    state = CompanionState.new("user-a")
    state.nova_current_mood = MoodState(energy=0.8, curiosity=0.85)
    intent = classify_social_intent("Tell me something interesting")

    modifiers = expression_modifiers(state, intent)

    assert modifiers["animated"] >= 0.75
    assert modifiers["curious"] >= 0.8


def test_casual_chat_invites_curiosity_after_first_interaction():
    from nova_companion.intent import classify_social_intent
    from nova_companion.models import CompanionState
    from nova_companion.social_reasoning import plan_social_response

    state = CompanionState.new("user-a")
    state.interaction_count = 1
    intent = classify_social_intent("Tell me something interesting")

    plan = plan_social_response(state, intent, [])

    assert plan.ask_follow_up is True
    assert plan.intensity >= 0.5
    assert "curiosity" in plan.reason_codes
