from __future__ import annotations

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

from v060_smart_memory_capture import classify_memory_event, MEMORY_TYPES


def root() -> Path:
    return ROOT


def _jsonl_path(memory_type: str) -> Path:
    return root() / "data" / "smart_memory" / f"{memory_type}.jsonl"


def _append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return items


def _backup_if_exists(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        backup = path.with_name(path.name + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(path, backup)


def process_message(
    message: str,
    answer: str | None = None,
    route: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a message and store it in the appropriate memory file."""
    classification = classify_memory_event(message, answer, route, context)
    event = {
        "id": datetime.now().strftime("v060_%Y%m%d_%H%M%S_%f"),
        "created_at": datetime.now().isoformat(),
        "message": message,
        "answer": answer or "",
        "route": route or "",
        "memory_type": classification["memory_type"],
        "confidence": classification["confidence"],
        "reason": classification["reason"],
        "extracted_fact": classification["extracted_fact"],
        "should_auto_save": classification["should_auto_save"],
        "should_require_approval": classification["should_require_approval"],
        "should_export_to_training": classification["should_export_to_training"],
        "tags": classification["tags"],
        "status": "approved" if classification["should_auto_save"] else "pending" if classification["should_require_approval"] else "logged",
    }

    mem_type = classification["memory_type"]
    storage_path = _jsonl_path(mem_type)
    _backup_if_exists(storage_path)
    _append_jsonl(storage_path, event)

    # If explicit user memory and safe, also update dictionary
    if mem_type == "explicit_user_memory" and classification["should_auto_save"]:
        _try_update_dictionary(classification["extracted_fact"])

    return {
        "event": event,
        "classification": classification,
        "stored_in": str(storage_path.relative_to(root())),
    }


def _try_update_dictionary(extracted_fact: str) -> None:
    """Try to extract a Q&A pair from explicit memory and add to dictionary."""
    fact = extracted_fact.strip().rstrip(".,!")
    dict_path = root() / "data" / "dictionary_memory" / "approved_answer_dictionary.json"
    if not dict_path.exists():
        return
    try:
        dictionary = json.loads(dict_path.read_text(encoding="utf-8"))
    except Exception:
        dictionary = {}

    # Patterns: "my X is Y" or "that X is Y" or "X means Y"
    m = __import__("re").search(r"(?i)(?:my |that |the )?([a-zA-Z_ ]{2,60}) is (.+)", fact)
    if m:
        key = m.group(1).strip().lower()
        val = m.group(2).strip()
        if key and val and key not in dictionary:
            dictionary[key] = val
            _backup_if_exists(dict_path)
            dict_path.write_text(json.dumps(dictionary, indent=2, ensure_ascii=False), encoding="utf-8")


def approve_pending(event_id: str) -> dict[str, Any]:
    """Move a pending_approval item to explicit_user_memory, or training_candidate to explicit."""
    pending = _read_jsonl(_jsonl_path("pending_approval_memory"))
    updated_pending = []
    approved_event = None

    for ev in pending:
        if ev.get("id") == event_id:
            ev["status"] = "approved"
            ev["approved_at"] = datetime.now().isoformat()
            approved_event = ev
            # Move to explicit_user_memory
            _backup_if_exists(_jsonl_path("explicit_user_memory"))
            _append_jsonl(_jsonl_path("explicit_user_memory"), ev)
        else:
            updated_pending.append(ev)

    _backup_if_exists(_jsonl_path("pending_approval_memory"))
    _write_jsonl(_jsonl_path("pending_approval_memory"), updated_pending)
    return {"approved": approved_event is not None, "event": approved_event}


def reject_pending(event_id: str) -> dict[str, Any]:
    """Mark a pending_approval item as rejected without deleting."""
    pending = _read_jsonl(_jsonl_path("pending_approval_memory"))
    updated = []
    found = False
    for ev in pending:
        if ev.get("id") == event_id:
            ev["status"] = "rejected"
            ev["rejected_at"] = datetime.now().isoformat()
            found = True
        updated.append(ev)
    _backup_if_exists(_jsonl_path("pending_approval_memory"))
    _write_jsonl(_jsonl_path("pending_approval_memory"), updated)
    return {"rejected": found}


def list_pending() -> list[dict[str, Any]]:
    return _read_jsonl(_jsonl_path("pending_approval_memory"))


def list_training_candidates() -> list[dict[str, Any]]:
    return _read_jsonl(_jsonl_path("training_candidate_memory"))


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def get_counts() -> dict[str, int]:
    counts = {}
    for mt in MEMORY_TYPES:
        counts[mt] = len(_read_jsonl(_jsonl_path(mt)))
    return counts
