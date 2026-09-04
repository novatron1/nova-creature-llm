from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_memory_v2 import NovaMemoryV2, selective_memory_update


def test_explicit_memory_persists_after_store_restart(tmp_path):
    database = tmp_path / "memory.db"
    first = NovaMemoryV2(database)
    saved = first.remember(
        "The user's preferred editor is VS Code.",
        memory_type="explicit",
        subject="user",
        predicate="preferred_editor",
    )
    first.close()

    second = NovaMemoryV2(database)
    found = second.search("preferred editor VS Code")
    second.close()

    assert found
    assert found[0].memory_id == saved.memory_id
    assert found[0].memory_type == "explicit"


def test_memory_correction_supersedes_old_record_and_keeps_history(tmp_path):
    store = NovaMemoryV2(tmp_path / "memory.db")
    old = store.remember(
        "The user's favorite color is blue.",
        memory_type="explicit",
        subject="user",
        predicate="favorite_color",
    )
    corrected = store.correct(old.memory_id, "The user's favorite color is purple.")

    assert store.get(old.memory_id).validity_status == "superseded"
    assert corrected.supersedes_id == old.memory_id
    assert "purple" in store.search("favorite color")[0].text.lower()
    assert len(store.version_history(old.memory_id)) >= 3


def test_memory_forget_removes_record_from_retrieval_but_keeps_audit(tmp_path):
    store = NovaMemoryV2(tmp_path / "memory.db")
    saved = store.remember("Temporary project codename is Firefly.", memory_type="project")
    assert store.forget(saved.memory_id) is True
    assert all(item.memory_id != saved.memory_id for item in store.search("Firefly"))
    assert store.get(saved.memory_id).validity_status == "forgotten"
    assert store.version_history(saved.memory_id)


def test_deduplication_and_explicit_priority(tmp_path):
    store = NovaMemoryV2(tmp_path / "memory.db")
    first = store.remember("User prefers local tools.", memory_type="semantic_user")
    duplicate = store.remember("User prefers local tools.", memory_type="explicit")
    store.remember("The project uses a local tool registry.", memory_type="project")

    assert duplicate.memory_id == first.memory_id
    results = store.search("local tools")
    assert results[0].memory_id == first.memory_id


def test_selective_memory_update_rejects_noise_and_saves_stable_facts(tmp_path):
    assert selective_memory_update("Nice weather today.", database=tmp_path / "a.db") is None
    saved = selective_memory_update(
        "Remember that I prefer local-first applications.",
        database=tmp_path / "b.db",
    )
    assert saved is not None
    assert saved.memory_type == "explicit"
    assert saved.importance == 1.0


def test_automatic_write_policy_blocks_ordinary_facts_but_keeps_explicit_commands(tmp_path):
    ordinary = selective_memory_update(
        "I prefer quiet notifications.",
        database=tmp_path / "ordinary.db",
        automatic_writes="explicit_only",
    )
    explicit = selective_memory_update(
        "Remember that I prefer quiet notifications.",
        database=tmp_path / "explicit.db",
        automatic_writes="explicit_only",
    )

    assert ordinary is None
    assert explicit is not None
    assert explicit.memory_type == "explicit"
