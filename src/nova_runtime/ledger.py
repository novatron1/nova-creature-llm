"""Append-only evidence ledger for Nova Creature autonomous runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import canonical_json, sha256_json


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    sequence: int
    event_type: str
    timestamp: str
    payload: dict[str, Any]
    payload_hash: str
    previous_hash: str
    entry_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


class EvidenceLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")
        self._entries = self._load_entries()

    def _load_entries(self) -> list[LedgerEntry]:
        entries: list[LedgerEntry] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = __import__("json").loads(line)
                entries.append(
                    LedgerEntry(
                        sequence=int(raw["sequence"]),
                        event_type=str(raw["event_type"]),
                        timestamp=str(raw["timestamp"]),
                        payload=dict(raw.get("payload") or {}),
                        payload_hash=str(raw["payload_hash"]),
                        previous_hash=str(raw["previous_hash"]),
                        entry_hash=str(raw["entry_hash"]),
                        metadata=dict(raw.get("metadata") or {}),
                    )
                )
            except Exception:
                continue
        return entries

    @property
    def last_entry(self) -> LedgerEntry | None:
        return self._entries[-1] if self._entries else None

    def append(self, *, event_type: str, payload: dict[str, Any], metadata: dict[str, Any] | None = None) -> LedgerEntry:
        previous_hash = self.last_entry.entry_hash if self.last_entry else "0" * 64
        sequence = (self.last_entry.sequence if self.last_entry else 0) + 1
        timestamp = datetime.now(timezone.utc).isoformat()
        payload_hash = sha256_json(payload)
        body = {
            "sequence": sequence,
            "event_type": event_type,
            "timestamp": timestamp,
            "payload_hash": payload_hash,
            "previous_hash": previous_hash,
        }
        entry_hash = sha256_json(body)
        entry = LedgerEntry(
            sequence=sequence,
            event_type=str(event_type),
            timestamp=timestamp,
            payload=dict(payload),
            payload_hash=payload_hash,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
            metadata=dict(metadata or {}),
        )
        self._entries.append(entry)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(entry.to_dict()) + "\n")
        return entry

    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)

