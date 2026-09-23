"""Regressions for the real conversation shaper, without a model or server."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nova_conversation_context import conversation_focus
from nova_natural_chat import build_conversation_state, shape_response, shape_verified_response
from nova_conversation_intelligence import understand_conversation_turn
from nova_response_repair import reviewed_direct_response


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("What's on your mind?", "I'm curious how the melody you mentioned changes the mood of a scene."),
        ("Would you mind explaining that?", "A chorus repeats the main idea of a song."),
        ("I changed my mind about dinner.", "Pizza instead of pasta? That works."),
        ("Do you enjoy music?", "I don't have human feelings, but I can explore the rhythms and stories in music with you."),
        ("What are you curious about?", "I'm curious about the painting you started. What made you choose those colors?"),
    ],
)
def test_shaper_keeps_substantive_social_answer(question, answer):
    assert shape_response(answer, question) == answer


@pytest.mark.parametrize("shape", [shape_response, shape_verified_response])
@pytest.mark.parametrize(
    "answer",
    [
        "I am unable to open your camera without permission.",
        "I cannot assist with breaking into someone else's account.",
        "I can't tell you I have human feelings. I can still talk with you about this.",
    ],
)
def test_personality_pass_preserves_refusal_meaning(shape, answer):
    assert shape(answer, "Would you mind doing that?") == answer


@pytest.mark.parametrize(
    "question",
    ["I enjoy running in the park.", "That song is good.", "I like train rides.", "Music makes me happy."],
)
def test_casual_sharing_does_not_invent_a_task_or_tool(question):
    state = build_conversation_state(question)
    assert state.intent != "task_request"
    assert state.user_stance != "directive"
    assert state.tool_candidates == []
    assert state.current_goal == ""


def test_long_day_is_acknowledged_as_strain_without_inventing_a_task():
    state = build_conversation_state("I had a long day.")
    assert state.intent == "social_reflection"
    assert state.dialogue_act == "acknowledge"
    focus = conversation_focus([
        {"role": "user", "content": "I had a long day."},
        {"role": "assistant", "content": "Sounds tiring. Want to unwind for a bit?"},
    ])
    assert focus.emotion == "strained"


@pytest.mark.parametrize("text", ["I made some tea.", "The download finished."])
def test_emotion_matching_does_not_find_mad_in_made_or_down_in_download(text):
    focus = conversation_focus([
        {"role": "user", "content": text},
        {"role": "assistant", "content": "Got it."},
    ])
    assert focus.emotion == ""


def test_repeated_feeling_reply_uses_recent_exchange_instead_of_same_script():
    repeated = "I'm here with you. Running steady, awake, and ready to talk. What's going on?"
    recent = [{"user": "How are you feeling today?", "nova": repeated}]
    shaped = shape_response(repeated, "How do u feel today?", recent)
    assert shaped != repeated
    assert "awake" not in shaped
    assert "human" in shaped or "feelings" in shaped
    assert shape_response(repeated, "How do u feel today?", []) == repeated


def test_followup_does_not_replace_non_nova_topic_with_personality_project():
    recent = [{
        "user": "Let's plan a picnic.",
        "nova": "We could pick a nearby park and bring sandwiches.",
    }]
    shaped = shape_response(
        "We should engage with stakeholders and offer personalized solutions.",
        "How can we do that?",
        recent,
    )
    assert "personality layer" not in shaped
    assert "Nova" not in shaped
    assert "park" in shaped or "picnic" in shaped


def test_followup_state_keeps_actual_recent_topic():
    state = build_conversation_state("How can we do that?", [
        {"user": "Let's plan a picnic.", "nova": "We could pick a nearby park."},
    ])
    assert "picnic" in state.topic
    assert state.dialogue_act == "resolve_context"


def test_new_social_topic_does_not_inherit_old_project_goal():
    state = build_conversation_state("I had a long day.", [
        {"user": "Fix the login form.", "nova": "The fix is done."},
    ])
    assert state.current_goal == ""


@pytest.mark.parametrize("text", ["I'm tired.", "I'm happy today.", "I had a long day.", "I'm exhausted."])
def test_casual_emotional_sharing_has_emotional_routing(text):
    decision = understand_conversation_turn(text)
    assert decision.intent_family == "emotional"
    assert decision.intent_subtype.startswith("user_")
    assert decision.reasoning_mode == "fast"
    assert reviewed_direct_response(decision)


@pytest.mark.parametrize("text", ["What are you curious about?", "What do you enjoy talking about?", "What interests you?"])
def test_self_interests_need_context_and_natural_generation_not_fact_reasoning(text):
    decision = understand_conversation_turn(text)
    assert decision.intent_family == "social"
    assert decision.context_required is True
    assert decision.factual_evidence_required is False
    assert decision.initial_model_tier == "small"


@pytest.mark.parametrize("text", ["How are you doing?", "How are u today?", "Can we just hang out for a minute?"])
def test_simple_checkins_and_companionship_have_a_reviewed_fast_response(text):
    decision = understand_conversation_turn(text)
    assert decision.intent_family in {"emotional", "social"}
    assert decision.initial_model_tier == "deterministic"
    assert reviewed_direct_response(decision)


@pytest.mark.parametrize("text", ["Good night Nova.", "I feel good.", "Can we talk?", "You are funny."])
def test_reviewed_responses_do_not_expose_mojibake(text):
    answer = reviewed_direct_response(understand_conversation_turn(text))
    assert answer
    assert "\u00e2\u20ac" not in answer
    assert "\ufffd" not in answer


def test_how_can_we_do_that_is_a_contextual_request_before_reasoning():
    decision = understand_conversation_turn("How can we do that?")
    assert decision.intent_family == "follow_up"
    assert decision.context_required is True
