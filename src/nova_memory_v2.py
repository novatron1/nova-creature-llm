"""Durable, selective, versioned SQLite memory for Nova."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Iterable
import uuid


MEMORY_V2_SCHEMA_VERSION = "2.0"
MEMORY_TYPES = frozenset(
    {
        "working",
        "episodic",
        "semantic_user",
        "project",
        "procedural",
        "reflection",
        "explicit",
    }
)
VALIDITY_STATES = frozenset({"active", "superseded", "forgotten", "expired", "disputed"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _hash(text: str) -> str:
    return hashlib.sha256(_canonical(text).encode("utf-8")).hexdigest()


@dataclass
class MemoryRecord:
    memory_id: str
    memory_type: str
    text: str
    subject: str | None
    predicate: str | None
    source: str
    created_at: str
    updated_at: str
    confidence: float
    importance: float
    validity_status: str
    expires_at: str | None
    sensitivity_level: str
    project_name: str | None
    tags: list[str] = field(default_factory=list)
    supersedes_id: str | None = None
    contradiction_status: str = "none"
    owner_id: str = "local-user"
    schema_version: str = MEMORY_V2_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NovaMemoryV2:
    """SQLite memory store with FTS search and immutable revision history."""

    def __init__(self, database: str | Path = "data/nova_memory.db") -> None:
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(
            str(self.path),
            timeout=10,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_records (
                    memory_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    subject TEXT,
                    predicate TEXT,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    importance REAL NOT NULL,
                    validity_status TEXT NOT NULL,
                    expires_at TEXT,
                    sensitivity_level TEXT NOT NULL,
                    project_name TEXT,
                    tags_json TEXT NOT NULL,
                    supersedes_id TEXT,
                    contradiction_status TEXT NOT NULL,
                    canonical_hash TEXT NOT NULL,
                    schema_version TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_owner_valid
                    ON memory_records(owner_id, validity_status, memory_type);
                CREATE INDEX IF NOT EXISTS idx_memory_subject_predicate
                    ON memory_records(owner_id, subject, predicate, validity_status);
                CREATE INDEX IF NOT EXISTS idx_memory_hash
                    ON memory_records(owner_id, canonical_hash, validity_status);
                CREATE TABLE IF NOT EXISTS memory_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    changed_at TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    memory_id UNINDEXED,
                    owner_id UNINDEXED,
                    text,
                    subject,
                    predicate,
                    tags
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _record(row: sqlite3.Row | None) -> MemoryRecord | None:
        if row is None:
            return None
        return MemoryRecord(
            memory_id=row["memory_id"],
            owner_id=row["owner_id"],
            memory_type=row["memory_type"],
            text=row["text"],
            subject=row["subject"],
            predicate=row["predicate"],
            source=row["source"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            confidence=float(row["confidence"]),
            importance=float(row["importance"]),
            validity_status=row["validity_status"],
            expires_at=row["expires_at"],
            sensitivity_level=row["sensitivity_level"],
            project_name=row["project_name"],
            tags=list(json.loads(row["tags_json"] or "[]")),
            supersedes_id=row["supersedes_id"],
            contradiction_status=row["contradiction_status"],
            schema_version=row["schema_version"],
        )

    def _save_history(self, record: MemoryRecord, action: str) -> None:
        revision = self._connection.execute(
            "SELECT COALESCE(MAX(revision), 0) + 1 FROM memory_history WHERE memory_id=?",
            (record.memory_id,),
        ).fetchone()[0]
        self._connection.execute(
            "INSERT INTO memory_history(memory_id, revision, action, snapshot_json, changed_at) VALUES(?,?,?,?,?)",
            (record.memory_id, revision, action, json.dumps(record.to_dict()), _now()),
        )

    def _refresh_fts(self, record: MemoryRecord) -> None:
        self._connection.execute("DELETE FROM memory_fts WHERE memory_id=?", (record.memory_id,))
        if record.validity_status == "active":
            self._connection.execute(
                "INSERT INTO memory_fts(memory_id, owner_id, text, subject, predicate, tags) VALUES(?,?,?,?,?,?)",
                (
                    record.memory_id,
                    record.owner_id,
                    record.text,
                    record.subject or "",
                    record.predicate or "",
                    " ".join(record.tags),
                ),
            )

    def remember(
        self,
        text: str,
        *,
        memory_type: str = "explicit",
        subject: str | None = None,
        predicate: str | None = None,
        source: str = "explicit_user_command",
        confidence: float = 1.0,
        importance: float = 0.8,
        expires_at: str | None = None,
        sensitivity_level: str = "private",
        project_name: str | None = None,
        tags: Iterable[str] = (),
        supersedes_id: str | None = None,
        owner_id: str = "local-user",
    ) -> MemoryRecord:
        value = re.sub(r"\s+", " ", str(text or "")).strip()
        if not value:
            raise ValueError("Memory text cannot be empty.")
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Unsupported memory type: {memory_type!r}")
        canonical_hash = _hash(value)
        with self._lock, self._connection:
            duplicate = self._connection.execute(
                "SELECT * FROM memory_records WHERE owner_id=? AND canonical_hash=? AND validity_status='active' LIMIT 1",
                (owner_id, canonical_hash),
            ).fetchone()
            if duplicate is not None:
                existing = self._record(duplicate)
                assert existing is not None
                return existing

            if subject and predicate:
                conflicts = self._connection.execute(
                    """
                    SELECT * FROM memory_records
                    WHERE owner_id=? AND subject=? AND predicate=? AND validity_status='active'
                    """,
                    (owner_id, subject, predicate),
                ).fetchall()
                for row in conflicts:
                    old = self._record(row)
                    if old and _canonical(old.text) != _canonical(value):
                        self._connection.execute(
                            "UPDATE memory_records SET contradiction_status='conflicting', updated_at=? WHERE memory_id=?",
                            (_now(), old.memory_id),
                        )

            timestamp = _now()
            record = MemoryRecord(
                memory_id="mem_" + uuid.uuid4().hex,
                owner_id=owner_id,
                memory_type=memory_type,
                text=value,
                subject=subject,
                predicate=predicate,
                source=source,
                created_at=timestamp,
                updated_at=timestamp,
                confidence=max(0.0, min(float(confidence), 1.0)),
                importance=max(0.0, min(float(importance), 1.0)),
                validity_status="active",
                expires_at=expires_at,
                sensitivity_level=sensitivity_level,
                project_name=project_name,
                tags=sorted({str(tag).strip().lower() for tag in tags if str(tag).strip()}),
                supersedes_id=supersedes_id,
            )
            self._connection.execute(
                """
                INSERT INTO memory_records(
                    memory_id, owner_id, memory_type, text, subject, predicate,
                    source, created_at, updated_at, confidence, importance,
                    validity_status, expires_at, sensitivity_level, project_name,
                    tags_json, supersedes_id, contradiction_status, canonical_hash,
                    schema_version
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record.memory_id, record.owner_id, record.memory_type, record.text,
                    record.subject, record.predicate, record.source, record.created_at,
                    record.updated_at, record.confidence, record.importance,
                    record.validity_status, record.expires_at, record.sensitivity_level,
                    record.project_name, json.dumps(record.tags), record.supersedes_id,
                    record.contradiction_status, canonical_hash, record.schema_version,
                ),
            )
            self._refresh_fts(record)
            self._save_history(record, "created")
            return record

    def get(self, memory_id: str, *, owner_id: str = "local-user") -> MemoryRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM memory_records WHERE memory_id=? AND owner_id=?",
                (memory_id, owner_id),
            ).fetchone()
        return self._record(row)

    def search(
        self,
        query: str,
        *,
        owner_id: str = "local-user",
        project_name: str | None = None,
        limit: int = 8,
        include_invalid: bool = False,
    ) -> list[MemoryRecord]:
        tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 1]
        rows: list[sqlite3.Row] = []
        with self._lock:
            if tokens:
                expression = " OR ".join(f'"{token}"' for token in tokens[:12])
                sql = (
                    "SELECT r.* FROM memory_fts f JOIN memory_records r ON r.memory_id=f.memory_id "
                    "WHERE memory_fts MATCH ? AND r.owner_id=? "
                )
                params: list[Any] = [expression, owner_id]
                if project_name:
                    sql += "AND r.project_name=? "
                    params.append(project_name)
                sql += (
                    "ORDER BY CASE r.memory_type WHEN 'explicit' THEN 0 WHEN 'semantic_user' THEN 1 "
                    "WHEN 'project' THEN 2 ELSE 3 END, r.importance DESC, r.updated_at DESC LIMIT ?"
                )
                params.append(max(1, min(int(limit), 100)))
                try:
                    rows = self._connection.execute(sql, params).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                sql = "SELECT * FROM memory_records WHERE owner_id=? "
                params = [owner_id]
                if not include_invalid:
                    sql += "AND validity_status='active' "
                if project_name:
                    sql += "AND project_name=? "
                    params.append(project_name)
                sql += (
                    "ORDER BY CASE memory_type WHEN 'explicit' THEN 0 WHEN 'semantic_user' THEN 1 "
                    "WHEN 'project' THEN 2 ELSE 3 END, importance DESC, updated_at DESC LIMIT ?"
                )
                params.append(max(1, min(int(limit), 100)))
                rows = self._connection.execute(sql, params).fetchall()
        return [record for row in rows if (record := self._record(row)) is not None]

    def list_relevant(self, query: str, **kwargs: Any) -> list[MemoryRecord]:
        return self.search(query, **kwargs)

    def update(self, memory_id: str, *, owner_id: str = "local-user", **updates: Any) -> MemoryRecord:
        allowed = {
            "text", "subject", "predicate", "confidence", "importance", "expires_at",
            "sensitivity_level", "project_name", "tags", "validity_status",
            "contradiction_status",
        }
        current = self.get(memory_id, owner_id=owner_id)
        if current is None:
            raise KeyError(memory_id)
        values = current.to_dict()
        values.update({key: value for key, value in updates.items() if key in allowed})
        if values["validity_status"] not in VALIDITY_STATES:
            raise ValueError("Invalid validity status.")
        values["updated_at"] = _now()
        values["tags"] = sorted({str(tag).strip().lower() for tag in values.get("tags") or []})
        with self._lock, self._connection:
            self._save_history(current, "before_update")
            self._connection.execute(
                """
                UPDATE memory_records SET text=?, subject=?, predicate=?, updated_at=?,
                    confidence=?, importance=?, validity_status=?, expires_at=?,
                    sensitivity_level=?, project_name=?, tags_json=?,
                    contradiction_status=?, canonical_hash=?
                WHERE memory_id=? AND owner_id=?
                """,
                (
                    values["text"], values["subject"], values["predicate"], values["updated_at"],
                    values["confidence"], values["importance"], values["validity_status"],
                    values["expires_at"], values["sensitivity_level"], values["project_name"],
                    json.dumps(values["tags"]), values["contradiction_status"],
                    _hash(values["text"]), memory_id, owner_id,
                ),
            )
            updated = self.get(memory_id, owner_id=owner_id)
            assert updated is not None
            self._refresh_fts(updated)
            self._save_history(updated, "updated")
            return updated

    def correct(
        self,
        memory_id: str,
        new_text: str,
        *,
        owner_id: str = "local-user",
        subject: str | None = None,
        predicate: str | None = None,
    ) -> MemoryRecord:
        old = self.get(memory_id, owner_id=owner_id)
        if old is None:
            raise KeyError(memory_id)
        self.update(
            memory_id,
            owner_id=owner_id,
            validity_status="superseded",
            contradiction_status="resolved",
        )
        return self.remember(
            new_text,
            memory_type="explicit",
            subject=subject if subject is not None else old.subject,
            predicate=predicate if predicate is not None else old.predicate,
            source="explicit_correction",
            confidence=1.0,
            importance=max(old.importance, 0.9),
            sensitivity_level=old.sensitivity_level,
            project_name=old.project_name,
            tags=old.tags,
            supersedes_id=memory_id,
            owner_id=owner_id,
        )

    def forget(self, memory_id: str, *, owner_id: str = "local-user") -> bool:
        if self.get(memory_id, owner_id=owner_id) is None:
            return False
        self.update(memory_id, owner_id=owner_id, validity_status="forgotten")
        return True

    def version_history(self, memory_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT revision, action, snapshot_json, changed_at FROM memory_history WHERE memory_id=? ORDER BY revision",
                (memory_id,),
            ).fetchall()
        return [
            {
                "revision": int(row["revision"]),
                "action": row["action"],
                "snapshot": json.loads(row["snapshot_json"]),
                "changed_at": row["changed_at"],
            }
            for row in rows
        ]

    def health_check(self) -> dict[str, Any]:
        with self._lock:
            count = self._connection.execute(
                "SELECT COUNT(*) FROM memory_records WHERE validity_status='active'"
            ).fetchone()[0]
        return {
            "ok": True,
            "schema_version": MEMORY_V2_SCHEMA_VERSION,
            "database": str(self.path),
            "active_records": int(count),
            "fts5": True,
        }


_DEFAULT_MEMORY: NovaMemoryV2 | None = None
_DEFAULT_LOCK = RLock()


def get_default_memory(database: str | Path | None = None) -> NovaMemoryV2:
    global _DEFAULT_MEMORY
    with _DEFAULT_LOCK:
        if database is not None:
            return NovaMemoryV2(database)
        if _DEFAULT_MEMORY is None:
            root = Path(__file__).resolve().parents[1]
            configured = os.environ.get("NOVA_MEMORY_V2_DATABASE", "data/nova_memory.db")
            path = Path(configured)
            if not path.is_absolute():
                path = root / path
            _DEFAULT_MEMORY = NovaMemoryV2(path)
        return _DEFAULT_MEMORY


def parse_explicit_memory(text: str) -> dict[str, Any] | None:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    patterns = (
        (r"(?i)^remember that\s+(.+)$", "explicit"),
        (r"(?i)^remember\s+(.+)$", "explicit"),
        (r"(?i)^my\s+([a-z][a-z0-9 _-]{1,40})\s+is\s+(.+)$", "semantic_user"),
        (r"(?i)^i prefer\s+(.+)$", "semantic_user"),
    )
    for pattern, memory_type in patterns:
        match = re.match(pattern, value)
        if not match:
            continue
        if len(match.groups()) == 2:
            predicate = _canonical(match.group(1)).replace(" ", "_")
            content = f"User {predicate.replace('_', ' ')} is {match.group(2).strip()}."
            return {
                "text": content,
                "memory_type": memory_type,
                "subject": "user",
                "predicate": predicate,
                "tags": ["explicit_user_memory"],
            }
        content = match.group(1).strip()
        return {
            "text": content,
            "memory_type": memory_type,
            "subject": "user",
            "predicate": None,
            "tags": ["explicit_user_memory"],
        }
    return None


def should_store_ordinary(text: str) -> bool:
    value = _canonical(text)
    if not value or len(value) > 500:
        return False
    if any(marker in value for marker in ("password", "api key", "secret token", "private key")):
        return False
    stable = (
        r"^i (?:prefer|like|use|work as|live in|am building)\b",
        r"^my [a-z0-9 _-]{2,40} is\b",
        r"^for this project\b",
    )
    return any(re.search(pattern, value) for pattern in stable)


def selective_memory_update(
    text: str,
    *,
    owner_id: str = "local-user",
    database: str | Path | None = None,
    automatic_writes: str = "selective",
) -> MemoryRecord | None:
    parsed = parse_explicit_memory(text)
    if parsed and (
        parsed.get("memory_type") == "explicit"
        or str(automatic_writes or "").lower()
        in {"selective", "automatic_safe_write"}
    ):
        return get_default_memory(database).remember(
            owner_id=owner_id,
            source=(
                "explicit_user_command"
                if parsed.get("memory_type") == "explicit"
                else "selective_conversation_write"
            ),
            importance=1.0 if parsed.get("memory_type") == "explicit" else 0.75,
            confidence=1.0 if parsed.get("memory_type") == "explicit" else 0.9,
            **parsed,
        )
    if str(automatic_writes or "").lower() not in {
        "selective",
        "automatic_safe_write",
    }:
        return None
    if not should_store_ordinary(text):
        return None
    return get_default_memory(database).remember(
        text,
        memory_type="semantic_user",
        owner_id=owner_id,
        source="selective_conversation_write",
        confidence=0.82,
        importance=0.65,
        tags=["selective_write"],
    )
