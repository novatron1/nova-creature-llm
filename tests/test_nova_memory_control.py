from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import nova_long_term_memory as ltm  # noqa: E402


def _isolated_memory(monkeypatch, tmp_path):
    monkeypatch.setattr(ltm, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(ltm, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(ltm, "BACKUP_DIR", str(tmp_path / "backups"))


def test_memory_control_lists_searches_and_sorts_pinned_first(monkeypatch, tmp_path):
    _isolated_memory(monkeypatch, tmp_path)
    city = ltm.add_memory("my city is Cincinnati")
    name = ltm.add_memory("my name is Mr Novatron")

    ltm.set_memory_pinned(name["memory_id"], True)
    records = ltm.list_memories()

    assert records[0]["memory_id"] == name["memory_id"]
    search = ltm.list_memories(query="cincinnati")
    assert len(search) == 1
    assert search[0]["memory_id"] == city["memory_id"]


def test_memory_control_updates_value_and_keywords(monkeypatch, tmp_path):
    _isolated_memory(monkeypatch, tmp_path)
    record = ltm.add_memory("my name is NovaTest")

    updated = ltm.update_memory_by_id(
        record["memory_id"],
        raw_text="my name is Mr Novatron",
        value="Mr Novatron",
        notes="corrected from control panel",
        trainable=True,
    )

    assert updated["extracted_value"] == "Mr Novatron"
    assert updated["notes"] == "corrected from control panel"
    assert updated["trainable"] is True
    assert "novatron" in updated["retrieval_keywords"]


def test_memory_control_soft_delete_restore_and_train_marker(monkeypatch, tmp_path):
    _isolated_memory(monkeypatch, tmp_path)
    record = ltm.add_memory("my signal word is blue comet")

    hidden = ltm.set_memory_active(record["memory_id"], False)
    assert hidden["active"] is False
    assert ltm.list_memories(active="active") == []
    assert len(ltm.list_memories(active="inactive")) == 1

    restored = ltm.set_memory_active(record["memory_id"], True)
    marked = ltm.mark_memory_trainable(record["memory_id"], True)

    assert restored["active"] is True
    assert marked["trainable"] is True
    assert marked["training_status"] == "queued"
