from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.memory import ProvenanceMemoryStore  # noqa: E402
from nova_runtime.memory_provenance import (  # noqa: E402
    build_provenance_record,
    write_provenance_memory,
)


class _Backend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def add_memory(self, content, **metadata):
        self.calls.append((content, dict(metadata)))
        return {"memory_id": "mem-1", "content": content}

    def edit_memory(self, query, new_text):
        self.calls.append((query, {"new_text": new_text}))
        return {"memory_id": "mem-1", "raw_text": new_text}, "old-value", "new-value"


def test_provenance_memory_record_contains_lineage() -> None:
    record = build_provenance_record(
        memory_id="mem_1",
        owner_id="local-user",
        source="agent_run",
        timestamp="2026-08-28T13:00:00Z",
        confidence=0.92,
        write_reason="verified project lesson",
        content="lesson learned",
        previous_version_hash="prev",
        rollback_point="ledger:42",
        ledger_entry_hash="entry:1",
        metadata={"project_id": "nova-creature"},
    )
    public = record.to_dict()
    assert public["rollback_point"] == "ledger:42"
    assert public["content_hash"]
    assert public["metadata"]["project_id"] == "nova-creature"


def test_memory_write_rejects_missing_provenance(tmp_path) -> None:
    store = ProvenanceMemoryStore(_Backend(), ledger_path=tmp_path / "memory-ledger.jsonl")
    with pytest.raises(ValueError):
        store.add_memory("lesson")


def test_provenance_write_attaches_audited_metadata(tmp_path) -> None:
    backend = _Backend()
    store = ProvenanceMemoryStore(backend, ledger_path=tmp_path / "memory-ledger.jsonl")
    result = write_provenance_memory(
        store,
        build_provenance_record(
            memory_id="",
            owner_id="local-user",
            source="agent_run",
            timestamp="2026-08-28T13:00:00Z",
            confidence=0.98,
            write_reason="verified project lesson",
            content="lesson learned",
            previous_version_hash="prev",
            rollback_point="ledger:42",
            metadata={"project_id": "nova-creature"},
        ),
    )

    assert backend.calls
    assert isinstance(result, dict)
    assert result["provenance"]["rollback_point"] == "ledger:42"
    assert result["provenance"]["ledger_entry_hash"]
    assert result["content_hash"] == result["provenance"]["content_hash"]
    assert (tmp_path / "memory-ledger.jsonl").read_text(encoding="utf-8").strip()
