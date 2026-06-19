"""v757_people_memory_events — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]

def people_memory_events(event=None):
    """Log every person memory event."""
    log_path = ROOT / "data/people/events.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if event is None:
        events = []
        if log_path.exists():
            with open(log_path) as f:
                for line in f:
                    line = line.strip()
                    if line: events.append(json.loads(line))
        return {"version": "v757_people_memory_events", "total_events": len(events),
                "recent_events": events[-20:], "status": "ok"}
    event["timestamp"] = datetime.now().isoformat()
    event["event_id"] = f"pe_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    with open(log_path, "a") as f:
        f.write(json.dumps(event) + "\n")
    return {"version": "v757_people_memory_events", "logged": event, "status": "ok"}


def main():
    import sys
    print(f"Nova v757_people_memory_events")
    r = people_memory_events()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
