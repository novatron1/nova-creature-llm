from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_answer_firewall import bypass_trace, evaluate_answer, recovery_response  # noqa: E402
from nova_conversation_context import (
    bounded_conversation_history,
    conversation_focus,
    previous_exchange,
    resolve_conversation_declaration,
    resolve_conversation_recall,
    resolve_contextual_followup,
    resolve_followup,
)  # noqa: E402


def test_bounded_history_uses_latest_complete_exchange_and_drops_current_user():
    history = bounded_conversation_history(
        {
            "conversation_history": [
                {"role": "system", "content": "ignored"},
                {"role": "user", "content": "How do I make ice cream?"},
                {"role": "assistant", "content": "Mix, churn, and freeze the base."},
                {"role": "user", "content": "tell me more"},
            ]
        },
        "tell me more",
    )

    assert history == [
        {"role": "user", "content": "How do I make ice cream?"},
        {"role": "assistant", "content": "Mix, churn, and freeze the base."},
    ]
    assert previous_exchange(history) == (
        "How do I make ice cream?",
        "Mix, churn, and freeze the base.",
    )


def test_conversation_recall_uses_latest_explicit_client_fact_without_a_model():
    history = [
        {"role": "user", "content": "The test number is 31."},
        {"role": "assistant", "content": "Okay."},
        {"role": "user", "content": "Correction: the test number is 32."},
        {"role": "assistant", "content": "Updated."},
    ]

    recall = resolve_conversation_recall(
        "What is the current test number?",
        history,
    )

    assert recall is not None
    assert recall.response == "32"
    assert recall.kind == "explicit_slot"
    assert recall.source_text == "Correction: the test number is 32."


def test_conversation_recall_can_resolve_a_relation_among_multiple_entities():
    history = [
        {
            "role": "user",
            "content": "Mina holds the brass key. Omar holds the glass key.",
        },
        {"role": "assistant", "content": "Got it."},
    ]

    recall = resolve_conversation_recall("Who holds the glass key?", history)

    assert recall is not None
    assert recall.response == "Omar"
    assert recall.kind == "relation"


def test_conversation_recall_handles_bounded_goal_location_reason_and_preference():
    examples = (
        (
            "What goal are we discussing?",
            "Our current goal is to reduce startup time.",
            "reduce startup time",
        ),
        (
            "What is beside the blue crate?",
            "The red robot is beside the blue crate.",
            "The red robot",
        ),
        (
            "Why did I miss it?",
            "I missed the bus because I left home late.",
            "You left home late",
        ),
        (
            "Which layout should we use now?",
            "Actually, switch to the spacious layout.",
            "spacious",
        ),
    )

    for prompt, prior_text, expected in examples:
        recall = resolve_conversation_recall(
            prompt,
            [
                {"role": "user", "content": prior_text},
                {"role": "assistant", "content": "Understood."},
            ],
        )
        assert recall is not None, prompt
        assert recall.response == expected, prompt


def test_conversation_recall_does_not_infer_from_assistant_text_or_unrelated_history():
    assistant_only = resolve_conversation_recall(
        "What is the codeword?",
        [{"role": "assistant", "content": "The codeword is unsafe_guess."}],
    )
    unrelated = resolve_conversation_recall(
        "What is the weather?",
        [
            {"role": "user", "content": "The codeword is SILVER_FOX_19."},
            {"role": "assistant", "content": "Noted."},
        ],
    )

    assert assistant_only is None
    assert unrelated is None


def test_temporary_conversation_declaration_is_acknowledged_without_persistence():
    codeword = resolve_conversation_declaration(
        "For this conversation, the codeword is SILVER_FOX_19."
    )
    color = resolve_conversation_declaration(
        "For this conversation, my temporary favorite color is teal."
    )
    stable_fact = resolve_conversation_declaration("My permanent favorite color is blue.")
    relation = resolve_conversation_declaration(
        "Mina holds the brass key. Omar holds the glass key."
    )
    assignment = resolve_conversation_declaration("Correction: the test number is 32.")
    location = resolve_conversation_declaration("The red robot is beside the blue crate.")
    reason = resolve_conversation_declaration(
        "I missed the bus because I left home late."
    )
    layout = resolve_conversation_declaration("Actually, switch to the spacious layout.")

    assert codeword is not None
    assert codeword.response == "Got it. The codeword for this conversation is SILVER_FOX_19."
    assert codeword.kind == "temporary_declaration"
    assert color is not None
    assert color.response == "Got it. Your temporary favorite color is teal."
    assert relation is not None
    assert relation.response == "Got it. I’ll keep those details in this conversation."
    assert assignment is not None
    assert location is not None
    assert reason is not None
    assert layout is not None
    assert layout.response == (
        "Got it. I’ll use the spacious layout as this conversation’s current preference."
    )
    assert stable_fact is None


def test_conversation_focus_skips_acknowledgement_and_keeps_real_subject():
    history = bounded_conversation_history(
        {
            "conversation_history": [
                {"role": "user", "content": "I think the world is flat based on a lot of things"},
                {"role": "assistant", "content": "Time zones and lunar eclipses are strong evidence against that."},
                {"role": "user", "content": "Okay"},
                {"role": "assistant", "content": "Got you. We can keep talking about it."},
            ]
        }
    )

    focus = conversation_focus(history)
    resolution = resolve_contextual_followup("But why?", history)

    assert focus.previous_user.startswith("I think the world is flat")
    assert focus.anchor_distance == 1
    assert resolution.kind == "explain_reasoning"
    assert resolution.previous_user == focus.previous_user
    assert "world is flat" in resolution.generation_prompt.lower()
    assert resolution.anchor_distance == 1


def test_contextual_followup_carries_recent_emotion_without_diagnosing():
    history = bounded_conversation_history(
        {
            "conversation_history": [
                {"role": "user", "content": "I am scared because I love her and want to be honest"},
                {"role": "assistant", "content": "Tell her honestly and give her room to respond."},
                {"role": "user", "content": "Okay"},
                {"role": "assistant", "content": "Take your time."},
            ]
        }
    )

    resolution = resolve_contextual_followup("What should I say to her?", history)

    assert resolution.kind == "referential"
    assert resolution.emotion == "anxious"
    assert resolution.subject.startswith("I am scared")
    assert "Recent user emotional signal: anxious" in resolution.generation_prompt
    assert "do not diagnose" in resolution.generation_prompt.lower()


def test_contextual_focus_does_not_turn_a_new_topic_into_a_followup():
    history = bounded_conversation_history(
        {
            "conversation_history": [
                {"role": "user", "content": "I am worried about my girlfriend"},
                {"role": "assistant", "content": "Tell me what happened."},
                {"role": "user", "content": "Okay"},
                {"role": "assistant", "content": "I'm listening."},
            ]
        }
    )

    resolution = resolve_contextual_followup("How do I make ice cream?", history)

    assert resolution.is_followup is False
    assert resolution.previous_user == "Okay"
    assert resolution.anchor_distance == 0


def test_conversation_focus_does_not_carry_emotion_from_an_older_subject():
    history = bounded_conversation_history(
        {
            "conversation_history": [
                {"role": "user", "content": "I am scared because I love my girlfriend"},
                {"role": "assistant", "content": "Be honest and give her time."},
                {"role": "user", "content": "I think the world is flat"},
                {"role": "assistant", "content": "Let's compare testable evidence."},
                {"role": "user", "content": "Okay"},
                {"role": "assistant", "content": "We can keep examining that subject."},
            ]
        }
    )

    focus = conversation_focus(history)
    resolution = resolve_contextual_followup("But why?", history)

    assert focus.subject == "I think the world is flat"
    assert focus.emotion == ""
    assert resolution.emotion == ""


def test_followup_resolution_turns_more_into_an_explicit_context_instruction():
    resolution = resolve_followup(
        "tell me more",
        "Why does ice cream need churning?",
        "Churning limits large ice crystals.",
    )

    assert resolution.kind == "expand"
    assert "Add useful new detail" in resolution.generation_prompt
    assert "Why does ice cream need churning?" in resolution.generation_prompt
    assert "Churning limits large ice crystals." in resolution.generation_prompt
    assert "go deeper" in resolution.fallback_response
    assert "large ice crystals" in resolution.immediate_response.lower()


def test_followup_resolution_handles_reactions_without_repeating_previous_answer():
    resolution = resolve_followup(
        "I like that",
        "Give me a project idea",
        "Build a local-first creature journal.",
    )

    assert resolution.kind == "positive_reaction"
    assert "glad" in resolution.immediate_response.lower()
    assert "Build a local-first creature journal" not in resolution.immediate_response


def test_followup_resolution_explains_previous_evidence_without_dismissing_user():
    previous_answer = (
        "[SCIENCE CHECK] Earth is not flat. The strongest checks are time zones, "
        "lunar eclipses, star visibility changing by latitude, and geodesy."
    )

    resolution = resolve_followup(
        "BUT WHY DO YOU SAY THAT",
        "I think the world is flat based on a lot of things",
        previous_answer,
    )

    assert resolution.kind == "explain_reasoning"
    assert "Explain the evidence and reasoning" in resolution.generation_prompt
    assert previous_answer in resolution.generation_prompt
    assert "confusing or off-topic" not in resolution.fallback_response
    assert "time zones" in resolution.immediate_response.lower()
    assert resolution.confidence == 0.98


def test_followup_resolution_treats_user_interpretation_as_continuation():
    resolution = resolve_followup(
        "TO ME THAT WOULD MAKE YOU LIKE A HUMAN",
        "DO YOU FEEL LIKE YOU ARE POWERFULL?",
        "I can reason, learn from you, remember context, use tools, and solve problems.",
    )

    assert resolution.kind == "perspective_response"
    assert "user's interpretation" in resolution.generation_prompt
    assert "DO YOU FEEL LIKE YOU ARE POWERFULL?" in resolution.generation_prompt
    assert "changing the subject" in resolution.fallback_response
    assert resolution.confidence == 0.96


def test_followup_resolution_anchors_hypothetical_and_next_step_turns():
    hypothetical = resolve_followup(
        "What if they say no?",
        "Ask the team whether they can move the deadline.",
        "Be direct about the constraint and offer two workable dates.",
    )
    next_step = resolve_followup(
        "Then what?",
        "Back up the project before migrating it.",
        "Create a verified export that excludes secrets and model weights.",
    )

    assert hypothetical.kind == "consequence"
    assert "hypothetical consequence" in hypothetical.generation_prompt
    assert "Ask the team whether they can move the deadline." in hypothetical.generation_prompt
    assert "Do not restate the follow-up as a question" in hypothetical.generation_prompt
    assert "reverse the user's stated goal" in hypothetical.generation_prompt
    assert next_step.kind == "next_step"
    assert "most practical next step" in next_step.generation_prompt
    assert "Create a verified export" in next_step.generation_prompt
    assert "respond to what actually happens" in hypothetical.immediate_response.lower()
    assert "verified export" in next_step.immediate_response.lower()


def test_followup_resolution_handles_relationship_rejection_without_canned_fallback():
    resolution = resolve_followup(
        "What if she doesn't say it back?",
        "I love my girlfriend",
        "Tell her honestly and gently, without pressuring her to answer the same way.",
    )

    assert resolution.kind == "consequence"
    assert "doesn't make your honesty a mistake" in resolution.immediate_response
    assert "give her room" in resolution.immediate_response.lower()


def test_followup_resolution_treats_and_then_as_a_next_step():
    resolution = resolve_followup(
        "And then?",
        "I love my girlfriend",
        "Tell her honestly and gently, without pressuring her to answer the same way.",
    )

    assert resolution.kind == "next_step"
    assert "without pressuring" in resolution.immediate_response.lower()


def test_followup_resolution_rechecks_a_challenged_answer():
    resolution = resolve_followup(
        "I don't think so",
        "Why is the sky blue?",
        "Shorter wavelengths scatter more strongly in the atmosphere.",
    )

    assert resolution.kind == "challenge"
    assert "Recheck the claim" in resolution.generation_prompt
    assert "acknowledge any real uncertainty" in resolution.generation_prompt
    assert "dismiss" not in resolution.fallback_response.lower()


def test_firewall_rejects_unrelated_personal_memory_but_accepts_requested_recall():
    rejected = evaluate_answer("How big is Earth?", "You live in Cincinnati.")
    accepted = evaluate_answer("Where do I live?", "You live in Cincinnati.")

    assert rejected.accepted is False
    assert "unrelated_personal_memory" in rejected.reasons
    assert accepted.accepted is True


def test_firewall_accepts_recent_name_recall_phrasing():
    accepted = evaluate_answer(
        "What name did I just give you?",
        "Your name is Live Test Novatron. I remember you.",
    )

    assert accepted.accepted is True
    assert "unrelated_personal_memory" not in accepted.reasons


def test_firewall_accepts_saved_name_recall_phrasing():
    accepted = evaluate_answer(
        "What name is saved for me?",
        "Your name is Live Test Three. I remember you.",
    )

    assert accepted.accepted is True
    assert "unrelated_personal_memory" not in accepted.reasons


def test_firewall_rejects_canned_general_and_domain_mismatch_answers():
    generic = evaluate_answer(
        "How do I make ice cream?",
        "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app. What do you want to do next?",
    )
    coding = evaluate_answer("How big is Earth?", "I can help with coding! What do you need?")

    assert generic.accepted is False
    assert "generic_fallback_mismatch" in generic.reasons
    assert coding.accepted is False
    assert "canned_domain_mismatch" in coding.reasons


def test_firewall_rejects_short_and_creative_canned_fallbacks():
    short = evaluate_answer(
        "Could a shadow dream?",
        "I'm here with you. Tell me what you want to do next.",
    )
    creative = evaluate_answer(
        "Imagine a city built inside a raindrop",
        "I can help with creative tasks! I have a creative preview builder and can generate SVG concepts.",
    )

    assert short.accepted is False
    assert creative.accepted is False
    assert "generic_fallback_mismatch" in short.reasons
    assert "generic_fallback_mismatch" in creative.reasons


def test_firewall_rejects_dismissive_why_followup_fallback():
    decision = evaluate_answer(
        "BUT WHY DO YOU SAY THAT",
        (
            "Because your statement is confusing or off-topic. Let's have a more "
            "focused conversation if that would help clarify things better."
        ),
    )

    assert decision.accepted is False
    assert "generic_fallback_mismatch" in decision.reasons


def test_firewall_rejects_canned_whats_on_your_mind_non_answer():
    decision = evaluate_answer(
        "TO ME THAT WOULD MAKE YOU LIKE A HUMAN",
        "Yeah, I'm here with you. Tell me what's on your mind.",
    )

    assert decision.accepted is False
    assert "generic_fallback_mismatch" in decision.reasons


def test_firewall_never_allows_a_replaceable_provider_to_rename_nova():
    rejected = evaluate_answer(
        "Quick check: what is your name?",
        "My name is Dolphin.",
        trace={"source": "provider_candidate"},
    )
    accepted = evaluate_answer(
        "Quick check: what is your name?",
        "I'm Nova Creature.",
        trace={"source": "provider_candidate"},
    )

    assert rejected.accepted is False
    assert "nova_identity_mismatch" in rejected.reasons
    assert recovery_response("Quick check: what is your name?", rejected) == "I'm Nova Creature."
    assert accepted.accepted is True


def test_firewall_rejects_relationship_echo_and_slogan_non_answers():
    echoed = evaluate_answer(
        "I KNOW THAT BUT WHAT SHOULD I SAY TO HER",
        "Okay, so you know that but... What should you say to her?",
    )
    slogan = evaluate_answer(
        "I LOVE HER",
        "I get you. Say it like you mean it; be clear, warm, and specific.",
    )

    assert echoed.accepted is False
    assert slogan.accepted is False
    assert "generic_fallback_mismatch" in echoed.reasons
    assert "generic_fallback_mismatch" in slogan.reasons


def test_firewall_rejects_cut_off_adapter_style_answers():
    first = evaluate_answer(
        "What if she doesn't say it back?",
        "I get you. If she doesn't",
    )
    second = evaluate_answer(
        "What does caring for someone mean?",
        "Right. I get you. That came",
    )

    assert first.accepted is False
    assert second.accepted is False
    assert "unfinished_response" in first.reasons
    assert "unfinished_response" in second.reasons


def test_firewall_rejects_visible_local_model_response_limit_marker():
    decision = evaluate_answer(
        "Compare local and remote memory across five areas.",
        (
            "Privacy stays local, but the remaining areas need review. "
            "Nova's local model reached its response limit before finishing."
        ),
    )

    assert decision.accepted is False
    assert "unfinished_response" in decision.reasons


def test_firewall_rejects_near_duplicate_followup_but_allows_new_detail():
    previous = "Churning limits large ice crystals and makes the finished ice cream smoother."
    repeated = evaluate_answer(
        "tell me more",
        "Churning limits large ice crystals and makes the finished ice cream smoother!",
        previous_answer=previous,
    )
    expanded = evaluate_answer(
        "tell me more",
        "Air folded in during churning also makes the texture lighter and easier to scoop.",
        previous_answer=previous,
    )

    assert repeated.accepted is False
    assert "repeated_previous_answer" in repeated.reasons
    assert expanded.accepted is True


def test_firewall_rejects_long_prompt_echo_but_not_a_short_greeting():
    echoed = evaluate_answer(
        "Imagine a city built inside a raindrop",
        "Imagine a city built inside a raindrop.",
    )
    greeting = evaluate_answer("hi", "Hi!")

    assert echoed.accepted is False
    assert "echoed_prompt" in echoed.reasons
    assert greeting.accepted is True


def test_firewall_rejects_near_prompt_paraphrase_but_allows_requested_repetition():
    paraphrase = evaluate_answer(
        "Imagine a village suspended inside a soap bubble",
        "A village suspended inside a soap bubble.",
    )
    requested = evaluate_answer(
        "Repeat after me: Nova is ready now",
        "Nova is ready now.",
    )

    assert paraphrase.accepted is False
    assert "prompt_paraphrase" in paraphrase.reasons
    assert requested.accepted is True


def test_firewall_accepts_relevant_answers_and_reports_raw_bypass_honestly():
    decision = evaluate_answer(
        "Can you help with Python?",
        "Yes, I can help with coding. Show me the Python error and the code around it.",
    )

    assert decision.accepted is True
    assert decision.as_trace()["status"] == "passed"
    assert bypass_trace() == {
        "checked": False,
        "status": "bypassed_raw",
        "accepted": True,
        "score": None,
        "reasons": [],
        "intercepted": False,
    }


def test_recovery_prefers_contextual_followup_over_generic_failure_text():
    decision = evaluate_answer(
        "another one",
        "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app.",
    )

    recovered = recovery_response(
        "another one",
        decision,
        contextual_fallback="Do you want another recipe or another example?",
    )

    assert recovered == "Do you want another recipe or another example?"


def test_provider_candidate_rejects_unsupported_numbers_for_factual_size_question():
    decision = evaluate_answer(
        "How big is Earth?",
        "Earth is 99,999 kilometers wide.",
        trace={"source": "provider_candidate", "numeric_verification_required": True},
    )

    assert decision.accepted is False
    assert "unverified_numeric_claim" in decision.reasons


def test_provider_candidate_accepts_number_already_grounded_in_previous_answer():
    decision = evaluate_answer(
        "tell me more",
        "That 12,742-kilometer diameter is measured through Earth's center.",
        previous_answer="Earth's diameter is about 12,742 kilometers.",
        trace={"source": "provider_candidate", "numeric_verification_required": True},
    )

    assert decision.accepted is True


def test_provider_candidate_allows_recipe_quantities_when_numeric_verification_not_required():
    decision = evaluate_answer(
        "How do I make ice cream?",
        "Mix 2 cups of cream with 1 cup of milk, then churn and freeze it.",
        trace={"source": "provider_candidate", "numeric_verification_required": False},
    )

    assert decision.accepted is True
