"""Provider-independent adapter around Nova's established long-term memory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .errors import PermissionDeniedError


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
