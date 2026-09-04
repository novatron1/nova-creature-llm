"""Provenance-aware memory writes for Nova Creature."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from .contracts import sha256_json
from .ledger import EvidenceLedger


@dataclass(frozen=True, slots=True)
class ProvenanceMemoryRecord:
    memory_id: str
    owner_id: str
    source: str
    timestamp: str
    confidence: float
    write_reason: str
    content: str
    content_hash: str
    previous_version_hash: str | None
    rollback_point: str | None
    ledger_entry_hash: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_provenance_record(
    *,
    memory_id: str,
    owner_id: str,
    source: str,
    timestamp: str,
    confidence: float,
    write_reason: str,
    content: str,
    previous_version_hash: str | None = None,
    rollback_point: str | None = None,
    ledger_entry_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProvenanceMemoryRecord:
    return ProvenanceMemoryRecord(
        memory_id=str(memory_id),
        owner_id=str(owner_id),
        source=str(source),
        timestamp=str(timestamp),
        confidence=float(confidence),
        write_reason=str(write_reason),
        content=str(content),
        content_hash=sha256_json(content),
        previous_version_hash=(str(previous_version_hash) if previous_version_hash else None),
        rollback_point=(str(rollback_point) if rollback_point else None),
        ledger_entry_hash=(str(ledger_entry_hash) if ledger_entry_hash else None),
        metadata=dict(metadata or {}),
    )


def validate_provenance_inputs(
    *,
    content: str,
    source: str,
    write_reason: str,
    confidence: float,
) -> None:
    if not str(content or "").strip():
        raise ValueError("content is required for provenance memory writes.")
    if not str(source or "").strip():
        raise ValueError("source is required for provenance memory writes.")
    if not str(write_reason or "").strip():
        raise ValueError("write_reason is required for provenance memory writes.")
    if not 0.0 <= float(confidence) <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0.")


def update_record_provenance(
    record: ProvenanceMemoryRecord,
    *,
    ledger_entry_hash: str,
    memory_id: str | None = None,
) -> ProvenanceMemoryRecord:
    return replace(
        record,
        memory_id=str(memory_id or record.memory_id),
        ledger_entry_hash=str(ledger_entry_hash),
    )


def write_provenance_memory(store: Any, record: ProvenanceMemoryRecord) -> Any:
    if hasattr(store, "write"):
        return store.write(
            record.content,
            source=record.source,
            write_reason=record.write_reason,
            confidence=record.confidence,
            previous_version_hash=record.previous_version_hash,
            rollback_point=record.rollback_point,
            metadata=dict(record.metadata),
        )
    if hasattr(store, "add_memory"):
        try:
            return store.add_memory(
                record.content,
                source=record.source,
                write_reason=record.write_reason,
                confidence=record.confidence,
                previous_version_hash=record.previous_version_hash,
                rollback_point=record.rollback_point,
                provenance=record.to_dict(),
            )
        except TypeError:
            return store.add_memory(record.content, source_command=record.source)
    raise AttributeError("store does not provide a provenance-compatible write method")


__all__ = [
    "EvidenceLedger",
    "ProvenanceMemoryRecord",
    "build_provenance_record",
    "update_record_provenance",
    "write_provenance_memory",
    "validate_provenance_inputs",
]
