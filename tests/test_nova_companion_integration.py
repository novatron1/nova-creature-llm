from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_managed_turn_attaches_companion_context_and_safe_trace(monkeypatch, tmp_path):
    import nova_enhanced_server as server
    from nova_companion.service import CompanionService

    service = CompanionService(database=tmp_path / "memory.db")
    captured = {}
    monkeypatch.setenv("NOVA_COMPANION_LAYER_ENABLED", "true")
    monkeypatch.setattr(server, "_get_companion_service", lambda: service, raising=False)

    def fake_brain_route(text, context=None):
        captured.update(context or {})
        return "Nova answer", {"source": "test", "answer_firewall": {"status": "passed"}}

    monkeypatch.setattr(server, "brain_route", fake_brain_route)
    response, trace = server._run_nova_chat_turn_impl(
        "What is on your mind?",
        {"user_id": "user-a", "conversation_id": "conv-1"},
    )

    assert response
    assert "companion_context" in captured
    assert trace["companion"]["enabled"] is True


def test_raw_adapter_turn_does_not_attach_or_persist_companion(monkeypatch, tmp_path):
    import nova_enhanced_server as server
    from nova_companion.service import CompanionService

    service = CompanionService(database=tmp_path / "memory.db")
    monkeypatch.setenv("NOVA_COMPANION_LAYER_ENABLED", "true")
    monkeypatch.setattr(server, "_get_companion_service", lambda: service, raising=False)
    monkeypatch.setattr(
        server,
        "_generate_raw_lora_adapter",
        lambda *args, **kwargs: {
            "raw_output": "raw",
            "local_llm_used": True,
            "model": "adapter",
        },
    )

    response, trace = server._run_nova_chat_turn_impl(
        "what is on your mind?",
        {
            "user_id": "user-a",
            "adapter_only_mode": True,
            "trained_adapter_only": True,
        },
    )

    assert response == "raw"
    assert "companion" not in trace
    assert service.store.load_state("user-a") is None


def test_synthesizer_adds_companion_context_only_when_supplied(monkeypatch):
    import nova_llm_synthesizer as synthesizer

    monkeypatch.setenv("NOVA_NATURAL_CHAT", "true")
    prompt, _ = synthesizer._build_prompt(
        {
            "system_prompt": "Original system.",
            "user_question": "What is on your mind?",
            "companion_context": {
                "relationship_stage": "familiar",
                "social_plan": {"primary_mode": "companionship", "tone": "warm_conversational"},
                "memories": [],
            },
        }
    )

    assert "NOVA COMPANION CONTEXT:" in prompt
    assert "relationship_stage: familiar" in prompt


def test_companion_continuity_follow_up_has_a_fast_bounded_answer():
    import nova_enhanced_server as server
    from nova_companion.service import CompanionService

    service = CompanionService(persistence=False)
    turn = service.begin_turn(
        "I am still thinking about the project we discussed",
        user_id="user-a",
        conversation_id="conv-1",
        context={},
        decision=type("Decision", (), {"intent_family": "project_tool"})(),
    )
    answer, trace = server._companion_continuity_fast_path(
        "I am still thinking about the project we discussed",
        turn,
    )
    assert answer
    assert "project" in answer.lower()
    assert trace["source"] == "companion_continuity"


def test_companion_stay_with_me_greeting_has_a_fast_bounded_answer():
    import nova_enhanced_server as server
    from nova_companion.service import CompanionService

    text = "Hi Nova, stay with me for this conversation."
    service = CompanionService(persistence=False)
    turn = service.begin_turn(
        text,
        user_id="user-a",
        conversation_id="conv-1",
        context={},
        decision=type("Decision", (), {"intent_family": "social"})(),
    )
    answer, trace = server._companion_continuity_fast_path(text, turn)

    assert answer
    assert "with you" in answer.lower()
    assert trace["source"] == "companion_continuity"


def test_companion_simple_advice_has_a_fast_bounded_answer():
    import nova_enhanced_server as server
    from nova_companion.service import CompanionService

    text = "Give me one practical next step."
    service = CompanionService(persistence=False)
    turn = service.begin_turn(
        text,
        user_id="user-a",
        conversation_id="conv-1",
        context={},
        decision=type("Decision", (), {"intent_family": "practical_support"})(),
    )
    answer, trace = server._companion_continuity_fast_path(text, turn)

    assert answer
    assert "next step" in answer.lower()
    assert trace["source"] == "companion_continuity"


def test_companion_simple_joke_has_a_fast_bounded_answer():
    import nova_enhanced_server as server
    from nova_companion.service import CompanionService

    text = "Give me a gentle joke about debugging this project."
    service = CompanionService(persistence=False)
    turn = service.begin_turn(
        text,
        user_id="user-a",
        conversation_id="conv-1",
        context={},
        decision=type("Decision", (), {"intent_family": "social"})(),
    )
    answer, trace = server._companion_continuity_fast_path(text, turn)

    assert answer
    assert "debug" in answer.lower() or "bug" in answer.lower()
    assert trace["source"] == "companion_continuity"
