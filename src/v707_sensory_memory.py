"""707 — Sensory Body Layer: Sensory Memory"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def sensory_memory(event=None):
    """Store a sensory event in memory and return the record."""
    path = ROOT / "data/sensory/sensory_memory.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if event is None:
        return {"version": "v707_sensory_memory", "events": [], "count": 0, "status": "ok"}
    event["memory_id"] = f"sem_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{event.get('source_type','unk')}"
    with open(path, "a") as f:
        f.write(json.dumps(event) + "\n")
    return {"version": "v707_sensory_memory", "stored": event, "path": str(path), "status": "ok"}


def main():
    print(f"Nova v707_sensory_memory")
    r = sensory_memory()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
