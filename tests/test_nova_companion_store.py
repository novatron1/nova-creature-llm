from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_companion_store_persists_state_and_relationship_memories(tmp_path):
    from nova_companion.models import CompanionState, RelationshipMemory
    from nova_companion.store import CompanionStore

    database = tmp_path / "memory.db"
    store = CompanionStore(database)
    state = CompanionState.new("user-a", now="2026-08-18T00:00:00+00:00")
    state.interaction_count = 3
    store.save_state(state)
    store.add_memory(
        RelationshipMemory.new(
            user_id="user-a",
            category="project",
            content="We are building Nova.",
            importance_score=0.9,
            confidence=0.9,
            source_conversation_id="conv-1",
            now="2026-08-18T00:00:00+00:00",
        )
    )

    restarted = CompanionStore(database)

    assert restarted.load_state("user-a").interaction_count == 3
    assert (
        restarted.search_memories("user-a", ["building", "nova"], limit=4)[0].category
        == "project"
    )
    assert restarted.search_memories("user-b", ["building", "nova"], limit=4) == []
