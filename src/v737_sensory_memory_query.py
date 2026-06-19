"""737 — Sensory Body Layer: Sensory Memory Query"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def sensory_memory_query(source_type=None, limit=20):
    """Query sensory memory by source type."""
    path = ROOT / "data/sensory/sensory_memory.jsonl"
    events = []
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    if source_type:
        events = [e for e in events if e.get("source_type") == source_type]
    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return {"version": "v737_sensory_memory_query", "source_type": source_type or "all",
            "count": len(events), "events": events[:limit], "status": "ok"}


def main():
    print(f"Nova v737_sensory_memory_query")
    r = sensory_memory_query()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
