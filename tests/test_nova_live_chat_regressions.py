"""Routing regressions from the live conversational trial; no model calls."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nova_conversation_context import resolve_contextual_followup
from nova_conversation_intelligence import understand_conversation_turn
from nova_response_repair import reviewed_direct_response


@pytest.mark.parametrize("prompt", [
    "Do you really have feelings, or is this how you talk?",
    "Do you actually experience emotions?",
    "Are your feelings real?",
    "Can you genuinely feel happy or sad?",
])
def test_questions_about_literal_feelings_get_a_direct_honest_boundary(prompt):
    decision = understand_conversation_turn(prompt)
    assert decision.intent_subtype == "self_experience_boundary"
    assert decision.initial_model_tier == "deterministic"
    answer = reviewed_direct_response(decision)
    assert "don't" in answer or "do not" in answer
    assert "feelings" in answer or "emotions" in answer
    assert "way a creature can" not in answer
    assert "How are you feeling" not in answer


@pytest.mark.parametrize("prompt", [
    "Do humans really have feelings?",
    "Explain how the brain processes emotions.",
    "Write a story about a robot that develops feelings.",
])
def test_self_experience_boundary_does_not_replace_science_or_fiction(prompt):
    assert understand_conversation_turn(prompt).intent_subtype != "self_experience_boundary"


@pytest.mark.parametrize("prompt", [
    "Ha, that's a good one.",
    "Haha, that was funny.",
    "That's hilarious.",
])
def test_positive_reaction_is_not_reinterpreted_as_an_old_topic(prompt):
    decision = understand_conversation_turn(prompt)
    assert decision.intent_family == "social"
    assert decision.intent_subtype == "positive_reaction"
    assert reviewed_direct_response(decision)


@pytest.mark.parametrize("prompt", [
    "Just chatting sounds good.",
    "Chatting for a bit sounds nice.",
    "Fair enough. It's still nice chatting with you.",
])
def test_casual_conversation_agreement_is_not_a_fresh_greeting(prompt):
    decision = understand_conversation_turn(prompt)
    assert decision.intent_family == "social"
    assert decision.intent_subtype != "greeting"
    answer = reviewed_direct_response(decision)
    assert answer
    assert "What's going on?" not in answer


def test_fragment_answer_stays_with_latest_question_and_generates_new_reply():
    history = [
        {"role": "user", "content": "How are you today?"},
        {"role": "assistant", "content": "I'm here. How are you?"},
        {"role": "user", "content": "I've been getting into music lately."},
        {"role": "assistant", "content": "What kind of music do you like?"},
    ]
    resolution = resolve_contextual_followup("Mostly mellow guitar and old soul.", history)
    assert resolution.is_followup
    assert resolution.previous_answer == "What kind of music do you like?"
    assert "Mostly mellow guitar and old soul." in resolution.generation_prompt
    assert resolution.immediate_response == ""


def test_a_new_topic_after_a_question_is_not_forced_into_a_short_answer():
    resolution = resolve_contextual_followup("Actually, I might go for a short walk instead.", [
        {"role": "user", "content": "I like music."},
        {"role": "assistant", "content": "What kind of music do you like?"},
    ])
    assert not resolution.is_followup


def test_open_conversational_updates_request_recent_context():
    decision = understand_conversation_turn("Mostly chores. I finally sat down with a cup of tea.")
    assert decision.context_required is True


def test_quiet_wind_down_update_uses_fast_reviewed_response():
    decision = understand_conversation_turn(
        "Mostly chores. I finally sat down with a cup of tea."
    )
    assert decision.intent_family == "social"
    assert decision.intent_subtype == "quiet_update"
    assert decision.initial_model_tier == "deterministic"
    assert reviewed_direct_response(decision)


@pytest.mark.parametrize("prompt", ["Why that kind?", "What were we talking about before the walk?"])
def test_referential_questions_request_conversation_context(prompt):
    decision = understand_conversation_turn(prompt)
    assert decision.intent_family == "follow_up"
    assert decision.context_required is True
