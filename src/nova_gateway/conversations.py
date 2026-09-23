"""Owner-scoped, privacy-bounded conversation archive for Nova clients."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


ARCHIVE_SCHEMA_VERSION = "1.0"
MAX_MESSAGES = 128
MAX_CONTENT = 8_000
MAX_TITLE = 160
MAX_RECORDS_PER_OWNER = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _safe_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    messages: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = item.get("content")
        # System/developer messages can carry private reasoning or control
        # instructions; archive only the visible user/assistant transcript.
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        clean = content.strip()[:MAX_CONTENT]
        if clean:
            messages.append({"role": role, "content": clean})
    return messages[-MAX_MESSAGES:]


class ConversationArchive:
    """Atomic JSON archive keyed by authenticated client and conversation ID."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).resolve() if path else None
        self._lock = RLock()
        self._records: dict[tuple[str, str], dict[str, Any]] = {}
        self._load()

    @staticmethod
    def _key(client_id: Any, conversation_id: Any) -> tuple[str, str]:
        return (_text(client_id, 160), _text(conversation_id, 160))

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in record.items() if key != "owner_id"}

    def _load(self) -> None:
        if not self.path or not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            rows = payload.get("conversations") if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                return
            loaded: dict[tuple[str, str], dict[str, Any]] = {}
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                owner, conversation = self._key(raw.get("owner_id"), raw.get("conversation_id"))
                if not owner or not conversation:
                    continue
                messages = _safe_messages(raw.get("messages"))
                loaded[(owner, conversation)] = self._make_record(
                    owner,
                    conversation,
                    title=raw.get("title"),
                    messages=messages,
                    created_at=raw.get("created_at"),
                    updated_at=raw.get("updated_at"),
                    archived=bool(raw.get("archived")),
                )
            self._records = loaded
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            # A malformed archive must never prevent Nova from starting.
            self._records = {}

    def _write_locked(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = sorted(
            self._records.values(),
            key=lambda row: str(row.get("updated_at") or ""),
            reverse=True,
        )
        payload = {"schema_version": ARCHIVE_SCHEMA_VERSION, "conversations": rows}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _make_record(
        owner_id: str,
        conversation_id: str,
        *,
        title: Any,
        messages: list[dict[str, str]],
        created_at: Any = None,
        updated_at: Any = None,
        archived: bool = False,
    ) -> dict[str, Any]:
        first_user = next((item["content"] for item in messages if item["role"] == "user"), "")
        clean_title = _text(title, MAX_TITLE) or _text(first_user, MAX_TITLE) or "New conversation"
        now = _now()
        return {
            "schema_version": ARCHIVE_SCHEMA_VERSION,
            "owner_id": owner_id,
            "conversation_id": conversation_id,
            "title": clean_title,
            "preview": _text(first_user or (messages[0]["content"] if messages else "No messages yet"), 240),
            "created_at": _text(created_at, 64) or now,
            "updated_at": _text(updated_at, 64) or now,
            "archived": bool(archived),
            "messages": messages,
            "message_count": len(messages),
        }

    def save(
        self,
        client_id: str,
        conversation_id: str,
        *,
        title: str | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        owner, conversation = self._key(client_id, conversation_id)
        if not owner or not conversation:
            raise ValueError("client_id and conversation_id are required")
        safe_messages = _safe_messages(messages)
        with self._lock:
            previous = self._records.get((owner, conversation))
            record = self._make_record(
                owner,
                conversation,
                title=title if title is not None else (previous or {}).get("title"),
                messages=safe_messages,
                created_at=(previous or {}).get("created_at"),
                archived=bool((previous or {}).get("archived")),
            )
            self._records[(owner, conversation)] = record
            owner_records = [key for key in self._records if key[0] == owner]
            for key in sorted(
                owner_records,
                key=lambda item: str(self._records[item].get("updated_at") or ""),
                reverse=True,
            )[MAX_RECORDS_PER_OWNER:]:
                self._records.pop(key, None)
            self._write_locked()
            return self._public(record)

    def get(self, client_id: str, conversation_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(self._key(client_id, conversation_id))
            return self._public(record) if record else None

    def list(
        self,
        client_id: str,
        *,
        query: str = "",
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        owner = _text(client_id, 160)
        needle = _text(query, 200).lower()
        with self._lock:
            rows = []
            for (record_owner, _), record in self._records.items():
                if record_owner != owner or (record.get("archived") and not include_archived):
                    continue
                haystack = " ".join(
                    [str(record.get("title") or ""), str(record.get("preview") or "")]
                    + [str(item.get("content") or "") for item in record.get("messages", [])]
                ).lower()
                if needle and needle not in haystack:
                    continue
                rows.append(self._public(record))
            rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
            return rows[: max(1, min(int(limit), 200))]

    def _set_archived(self, client_id: str, conversation_id: str, value: bool) -> bool:
        with self._lock:
            record = self._records.get(self._key(client_id, conversation_id))
            if not record:
                return False
            record["archived"] = bool(value)
            record["updated_at"] = _now()
            self._write_locked()
            return True

    def archive(self, client_id: str, conversation_id: str) -> bool:
        return self._set_archived(client_id, conversation_id, True)

    def restore(self, client_id: str, conversation_id: str) -> bool:
        return self._set_archived(client_id, conversation_id, False)

    def delete(self, client_id: str, conversation_id: str) -> bool:
        with self._lock:
            key = self._key(client_id, conversation_id)
            if key not in self._records:
                return False
            self._records.pop(key, None)
            self._write_locked()
            return True
