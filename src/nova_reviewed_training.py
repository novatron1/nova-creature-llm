"""Small, reviewed conversation lessons that are safe to use at runtime.

This is deliberately separate from raw feedback.  A correction only becomes a
runtime lesson after it has been reviewed and added to the approved data file.
The matcher is exact after conservative normalization. A reviewer may approve
additional explicit aliases, but loosely similar questions never receive an
unrelated memorized answer through fuzzy matching.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
MATCHER_VERSION = "1.1"
MAX_APPROVED_ALIASES = 12
DEFAULT_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "reviewed_conversation_training.json"


def normalize_prompt(value: Any) -> str:
    """Return the stable form used for exact reviewed-lesson matching."""

    text = str(value or "").lower().strip()
    text = text.replace("’", "'")
    text = re.sub(r"\bwhat's\b", "what is", text)
    text = re.sub(r"\bwhy's\b", "why is", text)
    text = re.sub(r"\bi'm\b", "i am", text)
    text = re.sub(r"\byou're\b", "you are", text)
    text = re.sub(r"\bu\b", "you", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class ReviewedReply:
    """One approved reply and its safe operational metadata."""

    lesson_id: str
    response: str
    category: str
    primary_role: str

    def to_dict(self) -> dict[str, str]:
        return {
            "lesson_id": self.lesson_id,
            "response": self.response,
            "category": self.category,
            "primary_role": self.primary_role,
        }


class ReviewedTrainingStore:
    """Load and cache explicitly approved conversation lessons."""

    def __init__(self, path: str | Path = DEFAULT_DATA_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._mtime_ns: int | None = None
        self._index: dict[str, ReviewedReply] = {}
        self._error: str | None = None

    def lookup(self, prompt: Any) -> ReviewedReply | None:
        """Return an exact approved lesson match, or ``None``."""

        key = normalize_prompt(prompt)
        if not key:
            return None
        self._refresh_if_needed()
        with self._lock:
            return self._index.get(key)

    def health_check(self) -> dict[str, Any]:
        """Report load status without exposing lesson contents."""

        self._refresh_if_needed()
        with self._lock:
            return {
                "ok": self._error is None,
                "schema_version": SCHEMA_VERSION,
                "matcher_version": MATCHER_VERSION,
                "lesson_count": len({reply.lesson_id for reply in self._index.values()}),
                "alias_count": len(self._index),
                "error": self._error,
            }

    def _refresh_if_needed(self) -> None:
        try:
            mtime_ns = self.path.stat().st_mtime_ns
        except OSError:
            mtime_ns = None
        with self._lock:
            if mtime_ns == self._mtime_ns and (self._index or self._error is not None):
                return
            self._mtime_ns = mtime_ns
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                self._index = self._build_index(payload)
                self._error = None
            except Exception as exc:
                self._index = {}
                self._error = f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _build_index(payload: Any) -> dict[str, ReviewedReply]:
        if not isinstance(payload, dict):
            raise ValueError("reviewed training data must be a JSON object")
        if str(payload.get("schema_version")) != SCHEMA_VERSION:
            raise ValueError(f"unsupported reviewed training schema: {payload.get('schema_version')!r}")
        entries = payload.get("entries")
        if not isinstance(entries, list):
            raise ValueError("reviewed training entries must be a list")

        index: dict[str, ReviewedReply] = {}
        for position, entry in enumerate(entries):
            if not isinstance(entry, dict) or entry.get("approved") is not True:
                continue
            lesson_id = str(entry.get("id") or "").strip()
            response = str(entry.get("response") or "").strip()
            aliases = entry.get("aliases")
            if not lesson_id or not response or not isinstance(aliases, list) or not aliases:
                raise ValueError(f"invalid approved lesson at position {position}")
            reply = ReviewedReply(
                lesson_id=lesson_id,
                response=response,
                category=str(entry.get("category") or "conversation"),
                primary_role=str(entry.get("primary_role") or "speech_output_transformer"),
            )
            for alias in aliases:
                key = normalize_prompt(alias)
                if not key:
                    raise ValueError(f"empty alias in approved lesson {lesson_id!r}")
                existing = index.get(key)
                if existing and existing.lesson_id != lesson_id:
                    raise ValueError(f"duplicate approved alias {alias!r}")
                index[key] = reply
        return index


_DEFAULT_STORE = ReviewedTrainingStore()
_WRITE_LOCK = threading.RLock()


def lookup_reviewed_reply(prompt: Any) -> dict[str, str] | None:
    """Look up a prompt in the default approved lesson store."""

    match = _DEFAULT_STORE.lookup(prompt)
    return match.to_dict() if match else None


def reviewed_training_health() -> dict[str, Any]:
    """Return health for the default reviewed lesson store."""

    return _DEFAULT_STORE.health_check()


def approve_reviewed_lesson(
    path: str | Path,
    *,
    lesson_id: str,
    prompt: str,
    response: str,
    category: str = "conversation",
    primary_role: str = "speech_output_transformer",
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    """Create or update one explicitly approved runtime lesson atomically.

    Alternate phrasings remain exact reviewed aliases. They are bounded and
    validated against every existing lesson before the file is replaced.
    """

    target = Path(path)
    clean_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(lesson_id or "")).strip("-")[:96]
    clean_prompt = str(prompt or "").strip()
    clean_response = str(response or "").strip()
    prompt_key = normalize_prompt(clean_prompt)
    if not clean_id or not prompt_key:
        raise ValueError("approved lesson needs an id and prompt")
    if not clean_response:
        raise ValueError("approved lesson needs a response")
    if aliases is not None and not isinstance(aliases, list):
        raise ValueError("approved lesson aliases must be a list")

    requested_aliases = [clean_prompt]
    requested_aliases.extend(str(alias or "").strip() for alias in (aliases or []))
    clean_aliases: list[str] = []
    seen_alias_keys: set[str] = set()
    for alias in requested_aliases:
        alias_key = normalize_prompt(alias)
        if not alias_key:
            raise ValueError("approved lesson aliases cannot be empty")
        if len(alias) > 500:
            raise ValueError("approved lesson aliases must be 500 characters or fewer")
        if alias_key in seen_alias_keys:
            continue
        seen_alias_keys.add(alias_key)
        clean_aliases.append(alias)
    if len(clean_aliases) > MAX_APPROVED_ALIASES:
        raise ValueError(f"approved lessons support at most {MAX_APPROVED_ALIASES} aliases")

    with _WRITE_LOCK:
        if target.exists():
            payload = json.loads(target.read_text(encoding="utf-8"))
        else:
            payload = {"schema_version": SCHEMA_VERSION, "entries": []}
        if not isinstance(payload, dict) or str(payload.get("schema_version")) != SCHEMA_VERSION:
            raise ValueError("reviewed lesson file has an unsupported schema")
        entries = payload.setdefault("entries", [])
        if not isinstance(entries, list):
            raise ValueError("reviewed lesson entries must be a list")

        selected: dict[str, Any] | None = None
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            aliases = entry.get("aliases") if isinstance(entry.get("aliases"), list) else []
            if str(entry.get("id") or "") == clean_id or any(normalize_prompt(alias) == prompt_key for alias in aliases):
                selected = entry
                break
        if selected is None:
            selected = {"id": clean_id, "aliases": []}
            entries.append(selected)

        stored_aliases = selected.get("aliases") if isinstance(selected.get("aliases"), list) else []
        stored_alias_keys = {normalize_prompt(alias) for alias in stored_aliases}
        for alias in clean_aliases:
            alias_key = normalize_prompt(alias)
            if alias_key not in stored_alias_keys:
                stored_aliases.append(alias)
                stored_alias_keys.add(alias_key)
        if len(stored_aliases) > MAX_APPROVED_ALIASES:
            raise ValueError(f"approved lessons support at most {MAX_APPROVED_ALIASES} aliases")
        selected.update(
            {
                "approved": True,
                "category": str(category or "conversation")[:80],
                "primary_role": str(primary_role or "speech_output_transformer")[:80],
                "aliases": stored_aliases,
                "response": clean_response,
                "reviewed_at": datetime.now().isoformat(),
            }
        )
        payload["updated_at"] = datetime.now().date().isoformat()
        payload.setdefault(
            "review_policy",
            "Only human-reviewed lessons belong here. Raw feedback is never loaded automatically.",
        )
        # Fail before writing if an alias collides with another lesson or the
        # resulting payload cannot be loaded safely at runtime.
        ReviewedTrainingStore._build_index(payload)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(target)
        return dict(selected)
