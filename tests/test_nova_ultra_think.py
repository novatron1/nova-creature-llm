from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_ultra_think as ultra


def test_ultra_think_trigger_detection_is_explicit():
    assert ultra.is_ultra_think_request("ultra think why does memory matter?")
    assert ultra.is_ultra_think_request("think hard about the best next move")
    assert ultra.is_ultra_think_request("deep think through this architecture")

    assert not ultra.is_ultra_think_request("what do you think about the app?")
    assert not ultra.is_ultra_think_request("answer this normally")


def test_strip_ultra_think_trigger_keeps_clean_question():
    assert ultra.strip_ultra_think_trigger("ultra think why memory matters") == "why memory matters"
    assert ultra.strip_ultra_think_trigger("think harder: fix the route") == "fix the route"
    assert ultra.strip_ultra_think_trigger("normal question") == "normal question"


def test_ultra_think_prompt_includes_recent_memory_and_route_context():
    prompt = ultra.build_ultra_think_prompt(
        "ultra think why did Nova sound reset?",
        recent_memory=[
            {
                "user": "Nova keeps sounding like a help desk.",
                "nova": "Yeah, I get what you mean.",
            }
        ],
        route_context="Route already chose deep reasoning.",
    )

    assert "SYSTEM:" in prompt
    assert "You are Nova Creature." in prompt
    assert "Do not reveal hidden chain-of-thought" in prompt
    assert "NOVA SELF-MODEL:" in prompt
    assert "operational self-awareness" in prompt
    assert "NOVA CURIOSITY DRIVE:" in prompt
    assert "OWNER STYLE PROFILE:" in prompt
    assert "RECENT CONVERSATION:" in prompt
    assert "User: Nova keeps sounding like a help desk." in prompt
    assert "Nova Creature: Yeah, I get what you mean." in prompt
    assert "ROUTE CONTEXT:\nRoute already chose deep reasoning." in prompt
    assert "CURRENT USER MESSAGE:\nwhy did Nova sound reset?" in prompt
    assert prompt.rstrip().endswith("NOVA CREATURE RESPONSE:")


def test_ultra_think_can_be_disabled(monkeypatch):
    monkeypatch.setenv("NOVA_ULTRA_THINK", "false")

    assert ultra.ultra_think_enabled() is False
    assert ultra.should_route_ultra_think("ultra think about memory") is False


def test_run_ultra_think_shapes_model_output_and_reports_trace(monkeypatch):
    monkeypatch.setenv("NOVA_ULTRA_THINK", "true")
    captured = {}

    def fake_llm_generate(context_packet):
        captured.update(context_packet)
        return (
            "As an AI language model, I am unable to answer casually. "
            "The issue is that Nova needs more conversation context.",
            True,
            None,
        )

    response, trace = ultra.run_ultra_think(
        "ultra think why does Nova forget the flow?",
        llm_generate_fn=fake_llm_generate,
    )

    assert captured["route"] == "ultra_think"
    assert captured["user_question"] == "why does Nova forget the flow?"
    assert "As an AI" not in response
    assert "unable" not in response.lower()
    assert "conversation context" in response
    assert trace["source"] == "ultra_think"
    assert trace["local_llm_synthesis_used"] is True
    assert trace["final_answer_source"] == "ultra_think"


def test_run_ultra_think_uses_memory_guard_before_llm(monkeypatch):
    monkeypatch.setenv("NOVA_ULTRA_THINK", "true")

    def fake_llm_generate(_context_packet):
        raise AssertionError("memory recall guard should answer before the LLM")

    response, trace = ultra.run_ultra_think(
        "ultra think what is my definitely missing code word?",
        llm_generate_fn=fake_llm_generate,
    )

    assert response == "I don't have your definitely missing code word saved yet."
    assert trace["source"] == "ultra_think_memory_guard"
    assert trace["local_llm_synthesis_used"] is False
