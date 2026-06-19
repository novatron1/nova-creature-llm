"""736 — Sensory Body Layer: Sensory Memory Store"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def sensory_memory_store(limit=50):
    """Retrieve stored sensory memory events."""
    path = ROOT / "data/sensory/sensory_memory.jsonl"
    events = []
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return {"version": "v736_sensory_memory_store", "total_events": len(events),
            "recent_events": events[:limit], "status": "ok"}


def main():
    print(f"Nova v736_sensory_memory_store")
    r = sensory_memory_store()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
