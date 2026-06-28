"""
Utility functions for Nova.
"""
import json
import hashlib
from datetime import datetime, timezone
from typing import Any


def timestamp() -> str:
    """Return ISO 8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str = "nova") -> str:
    """Generate a simple unique ID."""
    raw = f"{prefix}-{timestamp()}-{id({})}"
    return f"{prefix}-{hashlib.md5(raw.encode()).hexdigest()[:12]}"


def truncate(text: str, max_chars: int = 200) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def safe_json_serialize(obj: Any) -> str:
    """Serialize to JSON, handling dataclasses and enums."""
    def _default(o: Any) -> str:
        if hasattr(o, "__dataclass_fields__"):
            return {k: v for k, v in o.__dict__.items() if not k.startswith("_")}
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)
    return json.dumps(obj, default=_default, indent=2)


def load_jsonl(path: str) -> list[dict]:
    """Load a JSONL file, returning list of dicts."""
    records = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except FileNotFoundError:
        pass
    return records


def append_jsonl(path: str, record: dict) -> None:
    """Append a record to a JSONL file."""
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def count_tokens(text: str) -> int:
    """Rough token count estimation (characters / 4)."""
    return len(text) // 4
