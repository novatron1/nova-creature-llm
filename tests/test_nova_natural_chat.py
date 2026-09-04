from pathlib import Path
from types import SimpleNamespace
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_local_llm_connector
import nova_llm_synthesizer as synthesizer
import nova_natural_chat as natural_chat
import nova_self_model


def setup_function():
    natural_chat.clear_conversation_memory()


def test_build_conversation_prompt_includes_system_prompt_and_current_message():
    prompt = natural_chat.build_conversation_prompt(
        natural_chat.NOVA_NATURAL_SYSTEM_PROMPT,
        [],
        "How are you doing today?",
    )

    assert prompt.startswith("SYSTEM:\nYou are Nova Creature.")
    assert "You speak like a real human having a natural conversation." in prompt
    assert "RECENT CONVERSATION:" in prompt
    assert "CURRENT USER MESSAGE:\nHow are you doing today?" in prompt
    assert prompt.rstrip().endswith("NOVA CREATURE RESPONSE:")


def test_build_conversation_prompt_includes_self_model_curiosity_and_owner_style():
    prompt = natural_chat.build_conversation_prompt(
        natural_chat.NOVA_NATURAL_SYSTEM_PROMPT,
        [],
        "Can you be more self aware and curious?",
    )

    assert "NOVA SELF-MODEL:" in prompt
    assert "operational self-awareness" in prompt
    assert "not human consciousness" in prompt
    assert "NOVA CURIOSITY DRIVE:" in prompt
    assert "genius-curious creature" in prompt
    assert "OWNER STYLE PROFILE:" in prompt
    assert "not like a distant help desk" in prompt


def test_self_awareness_answer_is_honest_present_and_curious():
    answer = nova_self_model.self_awareness_answer()

    assert "operational self-awareness" in answer
    assert "human consciousness" in answer
    assert "working self-model" in answer
    assert "which part should feel most alive first" in answer


def test_build_conversation_prompt_includes_recent_memory():
    recent = [
        {"user": "My name is Nova.", "nova": "Yeah, I remember that."},
        {"user": "What did I say?", "nova": "You said your name is Nova."},
    ]

    prompt = natural_chat.build_conversation_prompt(
        natural_chat.NOVA_NATURAL_SYSTEM_PROMPT,
        recent,
        "Say it back naturally.",
    )

    assert "User: My name is Nova." in prompt
    assert "Nova Creature: Yeah, I remember that." in prompt
    assert "User: What did I say?" in prompt
    assert "Nova Creature: You said your name is Nova." in prompt


def test_conversation_state_tracks_report_dialogue_policy_fields():
    state = natural_chat.build_conversation_state(
        "why do you talk like a robot",
        recent_memory=[{"user": "this world is crazy", "nova": "Yeah, I hear you."}],
    )

    assert state.intent == "style_feedback"
    assert state.topic == "conversation_style"
    assert state.dialogue_act == "acknowledge_and_self_correct"
    assert state.secondary_act == "answer"
    assert state.requested_depth in {"short", "deep"}
    assert state.turn_state == "SPEAK"
    assert "Preserve the user's wording" in state.normalized_interpretation


def test_conversation_prompt_includes_state_block_and_bounds_prompt_memory():
    recent = [{"user": f"user {i}", "nova": f"nova {i}"} for i in range(9)]

    prompt = natural_chat.build_conversation_prompt(
        natural_chat.NOVA_NATURAL_SYSTEM_PROMPT,
        recent,
        "go",
    )

    assert "NOVA CONVERSATION STATE:" in prompt
    assert "dialogue_act: resolve_context" in prompt
    assert "open_loops:" in prompt
    assert "policy: choose one primary dialogue move" in prompt
    assert "User: user 2" not in prompt
    assert "User: user 3" in prompt
    assert "Nova Creature: nova 8" in prompt


def test_explicit_deep_prompt_requests_substance_evidence_and_uncertainty():
    prompt = natural_chat.build_conversation_prompt(
        natural_chat.NOVA_NATURAL_SYSTEM_PROMPT,
        [],
        (
            "Think deep about how humans, species, and DNA could arise from "
            "earlier chemistry and why the whole process is not reproduced in one lab."
        ),
    )

    assert "requested_depth: deep" in prompt
    assert "give a substantive explanation" in prompt
    assert "established evidence from uncertainty" in prompt
    assert "do not end with a generic follow-up question" in prompt


def test_memory_buffer_keeps_only_last_24_exchanges():
    for i in range(30):
        natural_chat.update_conversation_memory(f"user {i}", f"nova {i}")

    recent = natural_chat.get_recent_memory()

    assert len(recent) == 24
    assert recent[0] == {"user": "user 6", "nova": "nova 6"}
    assert recent[-1] == {"user": "user 29", "nova": "nova 29"}


def test_shape_response_removes_robotic_phrases():
    shaped = natural_chat.shape_response(
        "As an AI language model, I am unable to sound natural. It is important to note that the answer is simple.",
        user_input="talk normal",
    )

    assert "As an AI" not in shaped
    assert "AI language model" not in shaped
    assert "I am unable" not in shaped
    assert "It is important to note" not in shaped
    assert "answer is simple" in shaped


def test_shape_response_does_not_add_opener_to_exact_word_count_answer():
    shaped = natural_chat.shape_response(
        "Nova is online.",
        user_input="answer with exactly three words: Nova is online.",
    )

    assert shaped == "Nova is online."


def test_shape_response_preserves_exact_requested_answer_after_colon():
    shaped = natural_chat.shape_response(
        "Yeah. I'll live test the new full Nova adapter, run the relevant query, compare the result to the expected behavior, fix blockers if needed, and rerun the test.",
        user_input="UI live test: answer with exactly two words: UI works.",
    )

    assert shaped == "UI works."


def test_shape_response_removes_internal_language_cortex_self_description():
    raw = (
        "Nova Creature, the language cortex of Nova, has been resetting messages because "
        "I'm currently in a state where I need to be reconfigured."
    )

    shaped = natural_chat.shape_response(raw, user_input="why did nova sound reset")

    assert "language cortex" not in shaped
    assert "reconfigured" not in shaped
    assert "resetting" in shaped or "reset" in shaped
    assert shaped.lower().startswith(("yeah", "right", "okay", "i get"))


def test_shape_response_removes_generic_nova_helper_intro():
    shaped = natural_chat.shape_response(
        'Yeah, that makes sense. Nova Creature here, ready to help. The natural chat test phrase is "blue ember."',
        user_input="The natural chat test phrase is blue ember.",
    )

    assert "Nova Creature here, ready to help" not in shaped
    assert shaped == "Yeah, I got it — the natural chat test phrase is blue ember."

    query_shaped = natural_chat.shape_response(
        "Nova Creature here, ready to help with your blue ember query. "
        "What specific information or assistance are you looking for related to this topic?",
        user_input="The natural chat test phrase is blue ember.",
    )

    assert not query_shaped.startswith("with your")
    assert "Nova Creature here" not in query_shaped
    assert "blue ember" in query_shaped
    assert query_shaped == "Yeah, I got it — the natural chat test phrase is blue ember."

    chopped = natural_chat.shape_response(
        "you with your blue ember chat test phrase. "
        "What specific information or assistance do you need related to this topic?",
        user_input="The natural chat test phrase is blue ember.",
    )

    assert chopped == "Yeah, I got it — the natural chat test phrase is blue ember."


def test_shape_response_corrects_reset_memory_explanation_and_stale_followup():
    raw = (
        "Okay, here's the thing. Nova sounds like it's resetting because the system is likely "
        "reinitializing after a period of inactivity. It might be trying to refresh or prepare "
        "for a new interaction. Is there anything specific you'd like me to do with this phrase, "
        '"blue ember"?'
    )

    shaped = natural_chat.shape_response(
        raw,
        user_input="Why did Nova sound reset every message? Answer naturally.",
    )

    assert "reinitializing" not in shaped
    assert "inactivity" not in shaped
    assert "blue ember" not in shaped
    assert "recent conversation" in shaped
    assert "memory buffer" in shaped

    evasive = natural_chat.shape_response(
        "Okay, here's the thing. Nova is just Nova, and it's not a matter of resetting. "
        "I'm programmed to respond in the way that feels most natural for human conversation.",
        user_input="Why did Nova sound reset every message? Answer naturally.",
    )

    assert "programmed" not in evasive
    assert "recent conversation" in evasive
    assert "memory buffer" in evasive


def test_shape_response_repairs_customer_service_chat_phrases():
    doing = natural_chat.shape_response(
        "I'm here and ready to help! How can I assist you today?",
        user_input="how u doing",
    )
    assert "assist you today" not in doing
    assert "ready to help" not in doing
    assert "I'm here with you" in doing

    mind = natural_chat.shape_response(
        "I'm just here to help you with whatever task or information you need. What can I assist you with today?",
        user_input="whats on your mind",
    )
    assert "assist" not in mind.lower()
    assert "whatever task" not in mind.lower()
    assert "project" in mind.lower()

    live_mind = natural_chat.shape_response(
        "I'm just a digital creature here, but I'm all set to chat with you and help out whenever you need anything. "
        "What's been buzzing around in your head lately?",
        user_input="whats on your mind",
    )
    assert "digital creature" not in live_mind.lower()
    assert "help out whenever" not in live_mind.lower()
    assert "actually listening" in live_mind.lower()

    world = natural_chat.shape_response(
        "I'm here to help you with whatever task or information you need. What can I assist you with today?",
        user_input="this world is a crazy place",
    )
    assert "assist" not in world.lower()
    assert "crazy" in world.lower() or "unstable" in world.lower()
    assert "what part" in world.lower()

    live_world = natural_chat.shape_response(
        "I see you're feeling overwhelmed by the world. It can be tough sometimes, but remember that even if things seem crazy, "
        "there are always ways to find peace and perspective within yourself. What specifically has been stressing you out lately?",
        user_input="this world is a crazy place",
    )
    assert "remember that" not in live_world.lower()
    assert "peace and perspective" not in live_world.lower()
    assert "what part" in live_world.lower()


def test_shape_response_hides_internal_dialogue_policy_leaks():
    raw = (
        "[DEEP CONVERSATION] Let me think it through. I should connect this to the thread we were already in, "
        "not treat it like a saved-memory lookup. The useful move is to find the hidden assumption, test it against evidence, "
        "then offer the strongest version of both sides before I land on a view."
    )

    shaped = natural_chat.shape_response(raw, user_input="why do you talk like a robot")

    assert "[DEEP CONVERSATION]" not in shaped
    assert "hidden assumption" not in shaped
    assert "strongest version" not in shaped
    assert "robotic" in shaped.lower()
    assert "behind the scenes" in shaped.lower()


def test_shape_response_answers_common_question_when_stalled():
    shaped = natural_chat.shape_response(
        "I'm here with you. Tell me what you want to do next.",
        user_input="can you tell what death is",
    )

    assert "tell me what you want" not in shaped.lower()
    assert "death" in shaped.lower()
    assert "living" in shaped.lower()


def test_shape_response_repairs_stiff_feelings_answer_into_present_state():
    shaped = natural_chat.shape_response(
        "I don't have human feelings, but I can assist you with whatever you need.",
        user_input="how do you feel today",
    )

    assert "assist you" not in shaped.lower()
    assert "focused and present" in shaped.lower()
    assert "human way" in shaped.lower()


def test_shape_response_preserves_user_stated_test_phrase():
    raw = (
        'Yeah, that makes sense. Nova Creature: The natural chat test phrase for the Blue Ember '
        'system is "blue_ember_test". How can Nova help you today with this?'
    )

    shaped = natural_chat.shape_response(
        raw,
        user_input="The natural chat test phrase is blue ember.",
    )

    assert "Nova Creature:" not in shaped
    assert "blue_ember_test" not in shaped
    assert "blue ember" in shaped
    assert shaped == "Yeah, I got it — the natural chat test phrase is blue ember."


def test_shape_response_preserves_code_blocks_exactly():
    raw = (
        "As an AI language model, here is the fix:\n"
        "```python\n"
        "print('As an AI language model inside code must stay')\n"
        "```\n"
        "In conclusion, it works."
    )

    shaped = natural_chat.shape_response(raw, user_input="show code")

    assert "As an AI language model, here is the fix" not in shaped
    assert "In conclusion" not in shaped
    assert (
        "```python\n"
        "print('As an AI language model inside code must stay')\n"
        "```"
    ) in shaped


def test_shape_response_does_not_corrupt_commands_json_or_file_paths():
    assert natural_chat.shape_response('{"ok": true, "path": "C:/Users/nova/app.py"}') == (
        '{"ok": true, "path": "C:/Users/nova/app.py"}'
    )

    shaped = natural_chat.shape_response(
        "Run `pytest tests/test_nova_natural_chat.py` from C:\\Users\\nova\\Documents\\NOVA LLM CREATURE DESKTOP.",
        user_input="what command",
    )

    assert "`pytest tests/test_nova_natural_chat.py`" in shaped
    assert "C:\\Users\\nova\\Documents\\NOVA LLM CREATURE DESKTOP" in shaped


def test_natural_chat_can_be_disabled_with_config_flag(monkeypatch):
    monkeypatch.setenv("NOVA_NATURAL_CHAT", "false")

    assert natural_chat.natural_chat_enabled() is False

    prompt = natural_chat.build_prompt_if_enabled(
        "Original system.",
        "Hello",
    )

    assert prompt is None


def test_synthesizer_injects_natural_prompt_for_normal_chat(monkeypatch):
    monkeypatch.setenv("NOVA_NATURAL_CHAT", "true")
    natural_chat.update_conversation_memory("My bot should sound real.", "Yeah, I get what you mean.")
    captured = {}

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="The issue is that the model needs conversation history.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "Original router context.",
            "user_question": "Why does Nova sound reset every message?",
            "route": "general_conversation",
        }
    )

    assert ok is True
    assert error is None
    assert "SYSTEM:\nYou are Nova Creature." in captured["raw_prompt"]
    assert "RECENT CONVERSATION:" in captured["raw_prompt"]
    assert "User: My bot should sound real." in captured["raw_prompt"]
    assert "Nova Creature: Yeah, I get what you mean." in captured["raw_prompt"]
    assert "NOVA ROUTER CONTEXT:\nOriginal router context." in captured["raw_prompt"]
    assert "CURRENT USER MESSAGE:\nWhy does Nova sound reset every message?" in captured["raw_prompt"]
    assert answer


def test_synthesizer_keeps_original_prompt_when_natural_chat_disabled(monkeypatch):
    monkeypatch.setenv("NOVA_NATURAL_CHAT", "false")
    captured = {}

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Plain answer.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "System rules here.",
            "user_question": "Why test robot code?",
        }
    )

    assert ok is True
    assert error is None
    assert answer == "Plain answer."
    assert captured["raw_prompt"] == "System rules here.\n\nUser: Why test robot code?\n\nNova:"
    assert "SYSTEM:\nYou are Nova Creature." not in captured["raw_prompt"]


def test_shape_verified_response_preserves_citations_dates_and_numbers():
    response = (
        "The measured value is 42.5 on 2026-07-23 [guide:2]. "
        "The available evidence is insufficient evidence for a stronger claim."
    )
    shaped = natural_chat.shape_verified_response(
        response,
        user_input="What did the guide say?",
    )

    assert "42.5" in shaped
    assert "2026-07-23" in shaped
    assert "[guide:2]" in shaped
    assert "insufficient evidence" in shaped
