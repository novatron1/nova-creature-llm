from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nova_gateway.conversations import ConversationArchive


def test_conversation_archive_is_owner_scoped_and_supports_search_restore_delete(tmp_path):
    archive = ConversationArchive(tmp_path / "conversations.json")
    archive.save(
        "phone-a",
        "conv-1",
        title="Cat ideas",
        messages=[
            {"role": "user", "content": "Help me design a cat game"},
            {"role": "assistant", "content": "Let's start with movement."},
        ],
    )
    archive.save(
        "phone-b",
        "conv-2",
        title="Private",
        messages=[{"role": "user", "content": "Do not leak this"}],
    )

    assert [row["conversation_id"] for row in archive.list("phone-a", query="cat")] == ["conv-1"]
    assert archive.list("phone-a", query="private") == []
    archive.archive("phone-a", "conv-1")
    assert archive.list("phone-a") == []
    assert archive.list("phone-a", include_archived=True)[0]["archived"] is True
    archive.restore("phone-a", "conv-1")
    assert archive.list("phone-a")[0]["title"] == "Cat ideas"
    assert archive.delete("phone-a", "conv-1") is True
    assert archive.delete("phone-a", "conv-2") is False


def test_conversation_archive_writes_atomic_bounded_safe_records(tmp_path):
    path = tmp_path / "conversations.json"
    archive = ConversationArchive(path)
    archive.save(
        "client",
        "conv",
        title="  A title  ",
        messages=[
            {"role": "system", "content": "private reasoning must not persist"},
            {"role": "developer", "content": "secret"},
            {"role": "user", "content": " hello "},
            {"role": "assistant", "content": " answer "},
        ] * 100,
    )
    record = archive.get("client", "conv")
    assert record["title"] == "A title"
    assert all(item["role"] in {"user", "assistant"} for item in record["messages"])
    assert len(record["messages"]) <= 128
    assert "private reasoning" not in json.dumps(record)
    assert "secret" not in json.dumps(record)
    assert path.is_file()
    assert not path.with_suffix(".json.tmp").exists()


def test_conversation_archive_rejects_other_owner_and_malformed_records(tmp_path):
    archive = ConversationArchive(tmp_path / "conversations.json")
    with pytest.raises(ValueError):
        archive.save("client", "", title="bad", messages=[])
    archive.save("client", "conv", title="ok", messages=[])
    assert archive.get("other", "conv") is None
    assert archive.delete("other", "conv") is False
