from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_service_persists_accepted_turn_and_returns_safe_trace(tmp_path):
    from nova_companion.service import CompanionService

    service = CompanionService(database=tmp_path / "memory.db")
    turn = service.begin_turn(
        "We are building Nova together",
        user_id="user-a",
        conversation_id="conv-1",
        context={},
        decision=None,
    )
    trace = service.finalize_turn(
        turn,
        "That project matters to me too.",
        {"source": "reviewed_conversation_response"},
    )

    assert trace["enabled"] is True
    assert trace["memory_content_logged"] is False
    assert trace["interaction_count"] == 1
    assert service.store.load_state("user-a").interaction_count == 1


def test_service_disabled_persistence_does_not_write_state(tmp_path):
    from nova_companion.service import CompanionService

    service = CompanionService(database=tmp_path / "memory.db", persistence=False)
    turn = service.begin_turn(
        "hello there",
        user_id="user-a",
        conversation_id="conv-1",
        context={},
        decision=None,
    )
    trace = service.finalize_turn(turn, "Hi.", {})

    assert trace["state_persisted"] is False
    assert service.store.load_state("user-a") is None
