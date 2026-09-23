from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nova_conversation_context import resolve_conversation_recall
from nova_natural_chat import shape_response, shape_verified_response


def _history():
    return [
        {"role": "user", "content": "I was reading about nebulae."},
        {"role": "assistant", "content": "Nebulae are clouds of gas and dust."},
        {"role": "user", "content": "I might go for a picnic."},
        {"role": "assistant", "content": "Enjoy your picnic."},
        {"role": "user", "content": "Now I want to try painting."},
        {"role": "assistant", "content": "You could start with a simple landscape."},
    ]


def test_before_anchor_recall_quotes_an_actual_prior_turn_not_a_later_topic():
    recall = resolve_conversation_recall("What were we talking about before the picnic?", _history())
    assert recall is not None
    assert "Nebulae are clouds of gas and dust." in recall.response
    assert "I said" in recall.response
    assert "painting" not in recall.response
    assert "landscape" not in recall.response
    assert recall.source_text == "Nebulae are clouds of gas and dust."


def test_after_anchor_recall_uses_following_user_topic_and_keeps_ownership():
    recall = resolve_conversation_recall("What did I say after the picnic?", _history())
    assert recall is not None
    assert "Now I want to try painting." in recall.response
    assert "you said" in recall.response.lower()
    assert "Nebulae" not in recall.response


def test_temporal_recall_with_missing_anchor_explicitly_abstains():
    recall = resolve_conversation_recall("What were we discussing before the concert?", _history())
    assert recall is not None
    assert recall.confidence < 0.5
    assert "can't" in recall.response or "cannot" in recall.response
    assert "Nebulae" not in recall.response


def test_temporal_recall_does_not_answer_a_world_history_question():
    assert resolve_conversation_recall("What happened before the Renaissance?", _history()) is None


def test_temporal_recall_asks_which_anchor_when_multiple_user_mentions_exist():
    history = _history() + [{"role": "user", "content": "Another picnic might be fun."}]
    recall = resolve_conversation_recall("What were we discussing before the picnic?", history)
    assert recall is not None
    assert "which" in recall.response.lower()
    assert recall.source_text == ""


@pytest.mark.parametrize("shape", [shape_response, shape_verified_response])
def test_casual_shared_physical_activity_addresses_the_user_instead(shape):
    answer = shape(
        "It's a little rainy, though. Maybe we could enjoy a cozy indoor movie or a nice cup of tea instead?",
        "It's a little rainy, though.",
    )
    assert "we could" not in answer.lower()
    assert "you could" in answer.lower()
    assert not answer.startswith("It's a little rainy, though.")


def test_duplicate_leading_sentences_are_removed_when_a_new_answer_remains():
    prior = "Mellow guitar sounds relaxing. It's nice to unwind."
    answer = shape_response(
        prior + " For a quiet evening, try gentle acoustic music.",
        "What would suit a quiet evening?",
        [{"user": "Mostly mellow guitar.", "nova": prior}],
    )
    assert answer == "For a quiet evening, try gentle acoustic music."


def test_full_duplicate_answer_is_not_erased_or_replaced_with_filler():
    prior = "Mellow guitar sounds relaxing."
    assert shape_response(prior, "Tell me again.", [{"user": "What music?", "nova": prior}]) == prior


@pytest.mark.parametrize(("question", "answer"), [
    ("Quote the character's line.", '"Maybe we could drink some tea."'),
    ("Write a fictional scene.", "Maybe we could enjoy a cup of tea together."),
    ("Show code.", 'print("we could drink tea")'),
    ("What is the measured result?", "We could drink 250 ml of tea."),
    ("What did the tool report?", "Tool result: we could walk to the station."),
    ("I would like tea.", "I can't physically drink tea, but we can talk while you do."),
])
def test_casual_polish_preserves_quotes_fiction_code_values_tools_and_limits(question, answer):
    assert shape_response(answer, question) == answer


def test_current_user_echo_is_kept_when_user_explicitly_requests_repetition():
    answer = "Repeat after me: the sky is blue. The sky is blue."
    assert shape_response(answer, "Repeat after me: the sky is blue.") == answer
