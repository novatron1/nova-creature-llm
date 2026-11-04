from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nova_simulation_mode import build_simulation_response, maybe_add_funny_aside


def _context(**overrides):
    context = {
        "conversation_id": "simulation-test",
        "conversation_history": [],
        "simulation_mode": True,
        "personality": "warm",
    }
    context.update(overrides)
    return context


def test_simulation_mode_covers_requested_conversation_shapes():
    prompts = [
        "Can you give me some advice on planning a small project?",
        "How do I test an app?",
        "Why should I start with one feature?",
        "What about adding a backup plan?",
        "Is it true that this dry run changes no files?",
    ]
    for prompt in prompts:
        response, trace = build_simulation_response(prompt, _context())
        assert response
        assert response.startswith("Simulation")
        assert trace["simulation_mode"] is True
        assert trace["local_llm_synthesis_used"] is False
        assert trace["actions_executed"] is False


def test_simulation_classifier_handles_truth_checks_and_hyphenated_how_to():
    truth, truth_trace = build_simulation_response(
        "Is it true that simulation mode makes no real changes?", _context()
    )
    how_to, how_to_trace = build_simulation_response(
        "Give me a how-to for testing an app.", _context()
    )
    assert truth_trace["domain"] == "truth_check"
    assert "cannot verify unrelated live facts" in truth
    assert how_to_trace["domain"] == "how_to"
    assert how_to.startswith("Simulation how-to:")


def test_simulation_remembers_name_only_inside_supplied_history():
    response, trace = build_simulation_response(
        "What is my name in this test?",
        _context(
            conversation_history=[
                {"role": "user", "content": "My name is Mr Novatron."},
            ]
        ),
    )
    assert "Mr Novatron" in response
    assert trace["domain"] == "identity"


def test_funny_personality_is_bounded_and_skips_truth_checks():
    response, trace = maybe_add_funny_aside(
        "A concise answer.",
        "Give me general advice about my project.",
        _context(simulation_mode=False, personality="funny"),
    )
    assert trace["enabled"] is True
    assert trace["applied"] in {True, False}
    if trace["applied"]:
        assert "Playful Nova aside:" in response

    serious, serious_trace = maybe_add_funny_aside(
        "This claim is unverified.",
        "Is it true that the claim is current?",
        _context(simulation_mode=False, personality="funny"),
    )
    assert serious == "This claim is unverified."
    assert serious_trace["applied"] is False
    assert serious_trace["reason"] == "serious_or_truth_check"
