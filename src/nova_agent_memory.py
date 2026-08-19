"""
Agent memory for Nova's agentic wrapper.

This is separate from Nova's model/checkpoint memory. It stores small JSON
summaries of goals, results, tool traces, and useful task patterns.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import re


ROOT = Path(__file__).resolve().parents[1]
MEMORY_FILE = ROOT / "logs" / "agent_memory.json"
MAX_ITEMS_PER_BUCKET = 100


_SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9_-]{8,}|api[_-]?key\s*[:=]\s*\S+|token\s*[:=]\s*\S+|password\s*[:=]\s*\S+|secret\s*[:=]\s*\S+)"
)


def _redact(text) -> str:
    return _SECRET_RE.sub("[REDACTED]", str(text or ""))[:4000]


def _empty_memory() -> dict:
    return {
        "short_term_conversation": [],
        "active_goal_memory": [],
        "task_result_memory": [],
        "user_preference_memory": [],
        "tool_trace_memory": [],
    }


def _load_all() -> dict:
    if not MEMORY_FILE.exists():
        return _empty_memory()
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        base = _empty_memory()
        if isinstance(data, dict):
            for key in base:
                if isinstance(data.get(key), list):
                    base[key] = data[key]
        return base
    except Exception:
        return _empty_memory()


def _save_all(data: dict) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_limited(data: dict, bucket: str, item: dict) -> None:
    data.setdefault(bucket, []).append(item)
    data[bucket] = data[bucket][-MAX_ITEMS_PER_BUCKET:]


def save_agent_memory(state) -> dict:
    """Save compact, redacted memory from an agent turn."""
    data = _load_all()
    now = datetime.now().isoformat()

    goal = _redact(getattr(state, "current_goal", "") or getattr(state, "user_input", ""))
    final_answer = _redact(getattr(state, "final_answer", ""))
    trace_id = getattr(state, "trace_id", "")
    steps = [
        {
            "action_name": _redact(getattr(step, "action_name", "")),
            "status": _redact(getattr(step, "status", "")),
            "error": _redact(getattr(step, "error", "")),
        }
        for step in list(getattr(state, "steps_taken", []) or [])
    ]

    if goal:
        _append_limited(
            data,
            "active_goal_memory",
            {"timestamp": now, "trace_id": trace_id, "goal": goal},
        )

    if final_answer:
        _append_limited(
            data,
            "task_result_memory",
            {
                "timestamp": now,
                "trace_id": trace_id,
                "goal": goal,
                "summary": final_answer,
            },
        )

    if steps:
        _append_limited(
            data,
            "tool_trace_memory",
            {"timestamp": now, "trace_id": trace_id, "goal": goal, "steps": steps},
        )

    user_input = str(getattr(state, "user_input", "") or "")
    if re.search(r"\bprefer\b|\bremember that\b", user_input, re.IGNORECASE):
        _append_limited(
            data,
            "user_preference_memory",
            {"timestamp": now, "trace_id": trace_id, "summary": _redact(user_input)},
        )

    _save_all(data)
    return data


def load_relevant_memory(user_input) -> list[dict]:
    """Return small memory items with basic keyword overlap."""
    data = _load_all()
    q_words = {
        word.lower()
        for word in re.findall(r"[a-zA-Z0-9_]+", str(user_input or ""))
        if len(word) >= 4
    }
    if not q_words:
        return []

    matches = []
    for bucket, items in data.items():
        for item in list(items)[-MAX_ITEMS_PER_BUCKET:]:
            text = json.dumps(item, ensure_ascii=False).lower()
            score = sum(1 for word in q_words if word in text)
            if score:
                compact = dict(item)
                compact["memory_type"] = bucket
                compact["_score"] = score
                matches.append(compact)

    matches.sort(key=lambda item: item.get("_score", 0), reverse=True)
    for item in matches:
        item.pop("_score", None)
    return matches[:6]


def summarize_memory_if_too_large(max_items: int = 75) -> dict:
    """Trim oversized buckets while keeping recent items."""
    data = _load_all()
    changed = False
    for bucket, items in list(data.items()):
        if isinstance(items, list) and len(items) > max_items:
            data[bucket] = items[-max_items:]
            changed = True
    if changed:
        _save_all(data)
    return data


def clear_agent_memory() -> None:
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()

