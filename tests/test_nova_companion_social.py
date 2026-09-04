from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_social_intent_distinguishes_listening_joking_and_task_turns():
    from nova_companion.intent import classify_social_intent

    assert classify_social_intent("I just need you to listen").primary_mode == "venting"
    assert classify_social_intent("lol roast my terrible code").primary_mode == "joking"
    assert classify_social_intent("run the test suite").primary_mode == "task_execution"


def test_project_follow_up_stays_conversational_without_an_action_request():
    from types import SimpleNamespace

    from nova_companion.intent import classify_social_intent

    decision = SimpleNamespace(intent_family="project_tool")
    intent = classify_social_intent(
        "I am still thinking about the project we discussed",
        decision,
    )
    assert intent.primary_mode in {"casual_chat", "companionship"}


def test_practical_next_step_is_advice_not_generic_chat():
    from nova_companion.intent import classify_social_intent

    assert classify_social_intent("Give me one practical next step.").primary_mode == "advice"


def test_gentle_joke_request_is_joking():
    from nova_companion.intent import classify_social_intent

    assert classify_social_intent("Give me a gentle joke about debugging this project.").primary_mode == "joking"


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
    intent = classify_social_intent("we are making progress")
    for _ in range(100):
        state = adapt_state(state, intent, now="2026-08-18T00:00:00+00:00")

    assert state.familiarity_score <= 1.0
    assert state.interaction_count == 100
    assert stable_personality() == before
    assert state.nova_current_mood.energy <= 1.0


def test_companion_context_is_bounded_and_keeps_selected_memory_ids():
    from nova_companion.context_builder import build_companion_context
    from nova_companion.intent import classify_social_intent
    from nova_companion.models import CompanionState, RelationshipMemory
    from nova_companion.social_reasoning import plan_social_response

    state = CompanionState.new("user-a")
    memory = RelationshipMemory.new(
        "user-a", "project", "We are building Nova together", importance_score=0.9
    )
    intent = classify_social_intent("let's keep working on Nova")
    plan = plan_social_response(state, intent, [memory])
    context = build_companion_context("let's keep working on Nova", state, intent, plan, [memory])

    assert context.to_prompt_dict()["memories"][0]["memory_id"] == memory.memory_id
    assert len(str(context.to_prompt_dict())) <= 3000
