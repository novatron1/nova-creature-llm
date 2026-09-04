"""Additive SQLite persistence for Companion state and relationship memory."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Iterable

from .models import CompanionState, RelationshipMemory


def _tokens(values: Iterable[str]) -> set[str]:
    output: set[str] = set()
    for value in values:
        output.update(token for token in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(token) > 1)
    return output


def _recency(value: str) -> float:
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds() / 86400.0)
        return max(0.0, min(1.0, 1.0 / (1.0 + age_days / 30.0)))
    except (TypeError, ValueError):
        return 0.0


class CompanionStore:
    """Thread-safe owner-scoped store sharing Nova's existing memory DB."""

    def __init__(self, database: str | Path | None = None) -> None:
        if database is None:
            root = Path(__file__).resolve().parents[2]
            configured = Path(os.environ.get("NOVA_MEMORY_V2_DATABASE", "data/nova_memory.db"))
            database = configured if configured.is_absolute() else root / configured
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(str(self.path), timeout=10, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS companion_state (
                    user_id TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    relationship_stage TEXT NOT NULL,
                    familiarity_score REAL NOT NULL,
                    trust_score REAL NOT NULL,
                    interaction_count INTEGER NOT NULL,
                    first_interaction_at TEXT NOT NULL,
                    last_interaction_at TEXT NOT NULL,
                    preferred_tone TEXT NOT NULL,
                    humor_style TEXT NOT NULL,
                    conversational_energy REAL NOT NULL,
                    affection_style TEXT NOT NULL,
                    disagreement_style TEXT NOT NULL,
                    advice_style TEXT NOT NULL,
                    known_user_preferences_json TEXT NOT NULL,
                    recurring_topics_json TEXT NOT NULL,
                    shared_history_summary_json TEXT NOT NULL,
                    active_projects_json TEXT NOT NULL,
                    important_people_json TEXT NOT NULL,
                    unfinished_conversations_json TEXT NOT NULL,
                    recent_emotional_context_json TEXT NOT NULL,
                    nova_current_mood_json TEXT NOT NULL,
                    nova_personality_state_json TEXT NOT NULL,
                    personality_version TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS relationship_memories (
                    memory_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance_score REAL NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    last_referenced_at TEXT NOT NULL,
                    reference_count INTEGER NOT NULL,
                    source_conversation_id TEXT NOT NULL,
                    validity_status TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_relationship_memories_owner_valid
                    ON relationship_memories(user_id, validity_status);
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def load_state(self, user_id: str) -> CompanionState | None:
        owner = str(user_id or "").strip()[:160]
        if not owner:
            return None
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM companion_state WHERE user_id=?",
                (owner,),
            ).fetchone()
        return CompanionState.from_row(row) if row is not None else None

    def save_state(self, state: CompanionState) -> CompanionState:
        row = state.to_row()
        columns = list(row)
        placeholders = ",".join("?" for _ in columns)
        updates = ",".join(f"{column}=excluded.{column}" for column in columns if column != "user_id")
        with self._lock, self._connection:
            self._connection.execute(
                f"INSERT INTO companion_state ({','.join(columns)}) VALUES ({placeholders}) "
                f"ON CONFLICT(user_id) DO UPDATE SET {updates}",
                [row[column] for column in columns],
            )
        return state

    def add_memory(self, memory: RelationshipMemory) -> RelationshipMemory:
        values = {
            "memory_id": memory.memory_id,
            "user_id": memory.user_id,
            "category": memory.category,
            "content": memory.content,
            "importance_score": memory.importance_score,
            "confidence": memory.confidence,
            "created_at": memory.created_at,
            "last_referenced_at": memory.last_referenced_at,
            "reference_count": memory.reference_count,
            "source_conversation_id": memory.source_conversation_id,
            "validity_status": memory.validity_status,
        }
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO relationship_memories "
                "(memory_id,user_id,category,content,importance_score,confidence,created_at,last_referenced_at,reference_count,source_conversation_id,validity_status) "
                "VALUES (:memory_id,:user_id,:category,:content,:importance_score,:confidence,:created_at,:last_referenced_at,:reference_count,:source_conversation_id,:validity_status)",
                values,
            )
        return memory

    def search_memories(self, user_id: str, query_tokens: Iterable[str], *, limit: int = 4) -> list[RelationshipMemory]:
        owner = str(user_id or "").strip()[:160]
        wanted = _tokens(query_tokens)
        if not owner or not wanted:
            return []
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM relationship_memories WHERE user_id=? AND validity_status='active'",
                (owner,),
            ).fetchall()
        ranked: list[tuple[float, RelationshipMemory]] = []
        for row in rows:
            memory = RelationshipMemory.from_row(row)
            words = _tokens((memory.content, memory.category))
            overlap = len(wanted & words)
            if overlap == 0:
                continue
            relevance = min(1.0, overlap / max(1, min(len(wanted), 8)))
            score = (
                0.45 * relevance
                + 0.30 * memory.importance_score
                + 0.15 * memory.confidence
                + 0.10 * _recency(memory.last_referenced_at or memory.created_at)
            )
            ranked.append((score, memory))
        ranked.sort(key=lambda item: (item[0], item[1].importance_score, item[1].created_at), reverse=True)
        return [memory for _, memory in ranked[: max(1, min(int(limit), 4))]]

    def mark_referenced(self, user_id: str, memory_ids: Iterable[str]) -> None:
        owner = str(user_id or "").strip()[:160]
        ids = [str(item or "").strip()[:100] for item in memory_ids if str(item or "").strip()]
        if not owner or not ids:
            return
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock, self._connection:
            self._connection.executemany(
                "UPDATE relationship_memories SET reference_count=MIN(reference_count+1,100000), last_referenced_at=? WHERE user_id=? AND memory_id=? AND validity_status='active'",
                [(timestamp, owner, memory_id) for memory_id in ids],
            )

    def health(self) -> dict[str, object]:
        with self._lock:
            state_count = int(self._connection.execute("SELECT COUNT(*) FROM companion_state").fetchone()[0])
            memory_count = int(self._connection.execute("SELECT COUNT(*) FROM relationship_memories WHERE validity_status='active'").fetchone()[0])
        return {
            "ok": True,
            "schema_version": "1.0",
            "database": str(self.path),
            "state_count": state_count,
            "active_relationship_memories": memory_count,
            "content_logged": False,
        }
