"""Provider-independent adapter around Nova's established long-term memory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import PermissionDeniedError
from nova_runtime.contracts import sha256_json
from nova_runtime.ledger import EvidenceLedger
from nova_runtime.memory_provenance import (
    ProvenanceMemoryRecord,
    build_provenance_record,
    update_record_provenance,
    validate_provenance_inputs,
)


MEMORY_SCHEMA_VERSION = "1.0"
MEMORY_MODES = {"disabled", "read_only", "explicit_write", "automatic_safe_write"}
MEMORY_TYPES = {"working", "episodic", "semantic", "procedural", "artifact", "preference", "project"}


@dataclass
class NovaMemoryRecord:
    memory_id: str
    owner_id: str
    conversation_id: str | None
    project_id: str | None
    memory_type: str
    content: str
    summary: str
    source: str
    created_at: str
    updated_at: str
    confidence: float = 1.0
    importance: str = "normal"
    privacy: str = "private"
    permissions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    embedding_model: str | None = None
    embedding_version: str | None = None
    schema_version: str = MEMORY_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NovaMemoryStore(ABC):
    @abstractmethod
    def add_memory(self, content: str, **metadata: Any) -> NovaMemoryRecord | None: ...
    @abstractmethod
    def update_memory(self, memory_id: str, updates: dict[str, Any]) -> NovaMemoryRecord | None: ...
    @abstractmethod
    def delete_memory(self, memory_id: str) -> bool: ...
    @abstractmethod
    def get_memory(self, memory_id: str) -> NovaMemoryRecord | None: ...
    @abstractmethod
    def search_memory(self, query: str) -> list[NovaMemoryRecord]: ...
    @abstractmethod
    def export_memories(self) -> dict[str, Any]: ...
    @abstractmethod
    def import_memories(self, payload: dict[str, Any]) -> int: ...
    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...


class ExistingNovaMemoryStore(NovaMemoryStore):
    """Preserves the existing atomic memory implementation behind a stable API."""

    def __init__(self, module: Any = None, *, owner_id: str = "local-user", mode: str = "automatic_safe_write"):
        if module is None:
            import nova_long_term_memory as module
        if mode not in MEMORY_MODES:
            raise ValueError(f"Unsupported Nova memory mode {mode!r}.")
        self.module = module
        self.owner_id = owner_id
        self.mode = mode

    def _require_read(self) -> None:
        if self.mode == "disabled":
            raise PermissionDeniedError("Nova memory is disabled by policy.")

    def _require_write(self, explicit: bool = True) -> None:
        if self.mode in {"disabled", "read_only"}:
            raise PermissionDeniedError(f"Nova memory writes are blocked in {self.mode!r} mode.")
        if self.mode == "explicit_write" and not explicit:
            raise PermissionDeniedError("Nova memory requires an explicit write request.")

    def _adapt(self, item: dict[str, Any]) -> NovaMemoryRecord:
        now = datetime.now(timezone.utc).isoformat()
        content = str(item.get("raw_text") or item.get("value") or "")
        return NovaMemoryRecord(
            memory_id=str(item.get("memory_id") or ""), owner_id=self.owner_id,
            conversation_id=(item.get("metadata") or {}).get("conversation_id"), project_id=(item.get("metadata") or {}).get("project_id"),
            memory_type=str(item.get("category") or "semantic"), content=content,
            summary=str(item.get("value") or content), source=str(item.get("source_command") or "existing_nova_memory"),
            created_at=str(item.get("created_at") or now), updated_at=str(item.get("updated_at") or item.get("created_at") or now),
            importance=str(item.get("importance") or "normal"), privacy="private",
            tags=list(item.get("keywords") or []), metadata={"legacy_record": deepcopy(item)},
        )

    def add_memory(self, content: str, **metadata: Any) -> NovaMemoryRecord | None:
        self._require_write(explicit=bool(metadata.pop("explicit", True)))
        item = self.module.add_memory(content, source_command=metadata.pop("source", "memory_write"))
        return self._adapt(item) if item else None

    def update_memory(self, memory_id: str, updates: dict[str, Any]) -> NovaMemoryRecord | None:
        self._require_write()
        item = self.module.update_memory_by_id(memory_id, raw_text=updates.get("content"), importance=updates.get("importance"))
        return self._adapt(item) if item else None

    def delete_memory(self, memory_id: str) -> bool:
        self._require_write()
        return bool(self.module.set_memory_active(memory_id, False))

    def get_memory(self, memory_id: str) -> NovaMemoryRecord | None:
        self._require_read()
        for item in self.module.get_all(active_only=False):
            if item.get("memory_id") == memory_id:
                return self._adapt(item)
        return None

    def search_memory(self, query: str) -> list[NovaMemoryRecord]:
        self._require_read()
        return [self._adapt(item) for item in self.module.find_by_query(query)]

    def list_conversation_memories(self, conversation_id: str) -> list[NovaMemoryRecord]:
        return [item for item in self.search_memory("") if item.conversation_id == conversation_id]

    def export_memories(self) -> dict[str, Any]:
        self._require_read()
        return {"schema_version": MEMORY_SCHEMA_VERSION, "records": [self._adapt(item).to_dict() for item in self.module.get_all(active_only=False)]}

    def import_memories(self, payload: dict[str, Any]) -> int:
        self._require_write()
        count = 0
        for item in payload.get("records") or []:
            content = str(item.get("content") or "").strip()
            if content and self.add_memory(content, explicit=True, source="memory_import"):
                count += 1
        return count

    def migrate_schema(self) -> str:
        return MEMORY_SCHEMA_VERSION

    def health_check(self) -> dict[str, Any]:
        try:
            count = len(self.module.get_all(active_only=False))
            return {"ok": True, "store": "existing-nova-long-term-memory", "records": count, "mode": self.mode, "schema_version": MEMORY_SCHEMA_VERSION}
        except Exception as exc:
            return {"ok": False, "store": "existing-nova-long-term-memory", "error": str(exc), "mode": self.mode, "schema_version": MEMORY_SCHEMA_VERSION}


class ProvenanceMemoryStore:
    """Attach provenance metadata and ledger entries to memory writes."""

    def __init__(
        self,
        backend: Any,
        *,
        owner_id: str = "local-user",
        ledger_path: str | Path | None = None,
    ) -> None:
        self.backend = backend
        self.owner_id = owner_id
        self.ledger = EvidenceLedger(ledger_path or (Path("data") / "nova_memory_provenance.jsonl"))

    def __getattr__(self, name: str) -> Any:
        return getattr(self.backend, name)

    def add_memory(self, content: str, **metadata: Any) -> Any:
        source = str(
            metadata.pop("source", None)
            or metadata.pop("source_command", None)
            or ""
        )
        write_reason = str(metadata.pop("write_reason", None) or metadata.pop("reason", None) or source or "")
        confidence = metadata.pop("confidence", None)
        previous_version_hash = metadata.pop("previous_version_hash", None)
        rollback_point = metadata.pop("rollback_point", None)
        if confidence is None:
            confidence = 0.9 if source else 0.0
        return self.write(
            content,
            source=source,
            write_reason=write_reason,
            confidence=float(confidence),
            previous_version_hash=(str(previous_version_hash) if previous_version_hash else None),
            rollback_point=(str(rollback_point) if rollback_point else None),
            metadata=dict(metadata or {}),
        )

    def update_memory(self, memory_id: str, updates: dict[str, Any]) -> Any:
        source = str(updates.get("source") or updates.get("source_command") or "")
        write_reason = str(updates.get("write_reason") or updates.get("reason") or "")
        confidence = float(updates.get("confidence") or 0.0)
        return self.update(
            memory_id,
            dict(updates),
            source=source,
            write_reason=write_reason,
            confidence=confidence,
            previous_version_hash=updates.get("previous_version_hash"),
            rollback_point=updates.get("rollback_point"),
        )

    def update_memory_by_id(self, memory_id: str, **updates: Any) -> Any:
        return self.update_memory(memory_id, dict(updates))

    def edit_memory(self, query: str, new_text: str, **metadata: Any) -> Any:
        source = str(metadata.pop("source", None) or metadata.pop("source_command", None) or "")
        write_reason = str(metadata.pop("write_reason", None) or metadata.pop("reason", None) or source or "memory_edit")
        confidence = float(metadata.pop("confidence", 0.9 if source else 0.0) or 0.0)
        if hasattr(self.backend, "edit_memory"):
            backend_result = self.backend.edit_memory(query, new_text)
        else:
            backend_result = self.update_memory(query, {"content": new_text, **metadata})
        if isinstance(backend_result, tuple):
            record, old_value, new_value = backend_result
            content = str(getattr(record, "get", lambda *_: "")("raw_text", new_text) if hasattr(record, "get") else getattr(record, "raw_text", new_text))
        else:
            record = backend_result
            old_value = None
            new_value = None
            content = new_text
        provenance = build_provenance_record(
            memory_id=self._extract_memory_id(record),
            owner_id=self.owner_id,
            source=source or "memory_edit",
            timestamp=self._current_time(),
            confidence=confidence,
            write_reason=write_reason or "memory_edit",
            content=content,
            previous_version_hash=str(metadata.get("previous_version_hash") or old_value or ""),
            rollback_point=str(metadata.get("rollback_point") or query or ""),
            metadata={"query": query, "new_text": new_text, **dict(metadata or {})},
        )
        ledger_entry = self.ledger.append(
            event_type="memory_edit",
            payload={
                "memory_id": provenance.memory_id,
                "owner_id": self.owner_id,
                "source": provenance.source,
                "write_reason": provenance.write_reason,
                "confidence": provenance.confidence,
                "content_hash": provenance.content_hash,
                "previous_version_hash": provenance.previous_version_hash,
                "rollback_point": provenance.rollback_point,
            },
            metadata={"content_hash": provenance.content_hash},
        )
        provenance = update_record_provenance(
            provenance,
            ledger_entry_hash=ledger_entry.entry_hash,
            memory_id=provenance.memory_id,
        )
        if isinstance(record, dict):
            record = dict(record)
            record["provenance"] = provenance.to_dict()
            record["ledger_entry_hash"] = provenance.ledger_entry_hash
            return record, old_value, new_value
        if hasattr(record, "metadata") and isinstance(getattr(record, "metadata"), dict):
            metadata_copy = dict(getattr(record, "metadata"))
            metadata_copy["provenance"] = provenance.to_dict()
            try:
                record.metadata = metadata_copy
            except Exception:
                pass
        return record, old_value, new_value

    def delete_memory(self, memory_id: str, **metadata: Any) -> Any:
        source = str(metadata.pop("source", None) or metadata.pop("source_command", None) or "")
        write_reason = str(metadata.pop("write_reason", None) or metadata.pop("reason", None) or "")
        confidence = float(metadata.pop("confidence", 0.0) or 0.0)
        return self.delete(
            memory_id,
            source=source,
            write_reason=write_reason,
            confidence=confidence,
            rollback_point=metadata.pop("rollback_point", None),
        )

    @staticmethod
    def _current_time() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _attach_provenance(self, result: Any, record: ProvenanceMemoryRecord) -> Any:
        if isinstance(result, dict):
            payload = dict(result)
            payload["provenance"] = record.to_dict()
            payload["content_hash"] = record.content_hash
            payload["ledger_entry_hash"] = record.ledger_entry_hash
            return payload
        if hasattr(result, "metadata") and isinstance(getattr(result, "metadata"), dict):
            metadata = dict(getattr(result, "metadata"))
            metadata["provenance"] = record.to_dict()
            metadata["content_hash"] = record.content_hash
            metadata["ledger_entry_hash"] = record.ledger_entry_hash
            try:
                result.metadata = metadata
            except Exception:
                pass
        return result

    def write(
        self,
        content: str,
        *,
        source: str,
        write_reason: str,
        confidence: float,
        previous_version_hash: str | None = None,
        rollback_point: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        validate_provenance_inputs(
            content=content,
            source=source,
            write_reason=write_reason,
            confidence=confidence,
        )
        provenance = build_provenance_record(
            memory_id="",
            owner_id=self.owner_id,
            source=source,
            timestamp=self._current_time(),
            confidence=confidence,
            write_reason=write_reason,
            content=content,
            previous_version_hash=previous_version_hash,
            rollback_point=rollback_point,
            metadata=metadata,
        )
        backend_result = self._call_add_memory(content, source=source, metadata=metadata)
        memory_id = self._extract_memory_id(backend_result)
        ledger_entry = self.ledger.append(
            event_type="memory_write",
            payload={
                "memory_id": memory_id,
                "owner_id": self.owner_id,
                "source": source,
                "write_reason": write_reason,
                "confidence": confidence,
                "content_hash": provenance.content_hash,
                "previous_version_hash": previous_version_hash,
                "rollback_point": rollback_point,
            },
            metadata={"content_hash": provenance.content_hash},
        )
        provenance = update_record_provenance(
            provenance,
            ledger_entry_hash=ledger_entry.entry_hash,
            memory_id=memory_id,
        )
        return self._attach_provenance(backend_result, provenance)

    def update(
        self,
        memory_id: str,
        updates: dict[str, Any],
        *,
        source: str,
        write_reason: str,
        confidence: float,
        previous_version_hash: str | None = None,
        rollback_point: str | None = None,
    ) -> Any:
        validate_provenance_inputs(
            content=str(updates.get("content") or updates.get("raw_text") or ""),
            source=source,
            write_reason=write_reason,
            confidence=confidence,
        )
        backend_result = self._call_update_memory(memory_id, updates)
        content = str(updates.get("content") or updates.get("raw_text") or "")
        provenance = build_provenance_record(
            memory_id=memory_id,
            owner_id=self.owner_id,
            source=source,
            timestamp=self._current_time(),
            confidence=confidence,
            write_reason=write_reason,
            content=content,
            previous_version_hash=previous_version_hash,
            rollback_point=rollback_point,
            metadata={"updates": dict(updates)},
        )
        ledger_entry = self.ledger.append(
            event_type="memory_update",
            payload={
                "memory_id": memory_id,
                "owner_id": self.owner_id,
                "source": source,
                "write_reason": write_reason,
                "confidence": confidence,
                "content_hash": provenance.content_hash,
                "previous_version_hash": previous_version_hash,
                "rollback_point": rollback_point,
            },
            metadata={"content_hash": provenance.content_hash},
        )
        provenance = update_record_provenance(
            provenance,
            ledger_entry_hash=ledger_entry.entry_hash,
            memory_id=memory_id,
        )
        return self._attach_provenance(backend_result, provenance)

    def delete(
        self,
        memory_id: str,
        *,
        source: str,
        write_reason: str,
        confidence: float,
        rollback_point: str | None = None,
    ) -> Any:
        validate_provenance_inputs(
            content=memory_id,
            source=source,
            write_reason=write_reason,
            confidence=confidence,
        )
        backend_result = self._call_delete_memory(memory_id)
        ledger_entry = self.ledger.append(
            event_type="memory_delete",
            payload={
                "memory_id": memory_id,
                "owner_id": self.owner_id,
                "source": source,
                "write_reason": write_reason,
                "confidence": confidence,
                "rollback_point": rollback_point,
            },
        )
        if isinstance(backend_result, dict):
            result = dict(backend_result)
            result["ledger_entry_hash"] = ledger_entry.entry_hash
            return result
        return backend_result

    def _extract_memory_id(self, result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("memory_id") or result.get("id") or "")
        return str(getattr(result, "memory_id", "") or getattr(result, "id", "") or "")

    def _call_add_memory(self, content: str, *, source: str, metadata: dict[str, Any] | None) -> Any:
        if hasattr(self.backend, "add_memory"):
            try:
                return self.backend.add_memory(content, explicit=True, source=source, **dict(metadata or {}))
            except TypeError:
                try:
                    return self.backend.add_memory(content, source_command=source)
                except TypeError:
                    return self.backend.add_memory(content)
        raise AttributeError("backend does not provide add_memory")

    def _call_update_memory(self, memory_id: str, updates: dict[str, Any]) -> Any:
        if hasattr(self.backend, "update_memory"):
            return self.backend.update_memory(memory_id, dict(updates))
        if hasattr(self.backend, "update_memory_by_id"):
            payload = dict(updates)
            return self.backend.update_memory_by_id(memory_id, raw_text=payload.get("content"), value=payload.get("value"), notes=payload.get("notes"))
        raise AttributeError("backend does not provide update_memory")

    def _call_delete_memory(self, memory_id: str) -> Any:
        if hasattr(self.backend, "delete_memory"):
            return self.backend.delete_memory(memory_id)
        if hasattr(self.backend, "set_memory_active"):
            return self.backend.set_memory_active(memory_id, False)
        raise AttributeError("backend does not provide delete_memory")


def wrap_provenance_memory_backend(
    backend: Any,
    *,
    owner_id: str = "local-user",
    ledger_path: str | Path | None = None,
) -> ProvenanceMemoryStore:
    return ProvenanceMemoryStore(backend, owner_id=owner_id, ledger_path=ledger_path)
