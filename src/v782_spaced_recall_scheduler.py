"""v782_spaced_recall_scheduler — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


_spaced_schedule = {}

def spaced_recall_scheduler(action="status", lesson_id=None):
    """Schedule repeat tests at intervals."""
    now = datetime.now()
    if action == "schedule" and lesson_id:
        _spaced_schedule[lesson_id] = {
            "immediate": now.isoformat(),
            "same_session": None,
            "next_run": None,
            "long_term_review": None,
            "current_interval": 0
        }
        return {"version": "v782_spaced_recall_scheduler", "scheduled": lesson_id, "status": "ok"}
    elif action == "advance" and lesson_id and lesson_id in _spaced_schedule:
        entry = _spaced_schedule[lesson_id]
        entry["current_interval"] += 1
        if entry["current_interval"] == 1:
            entry["same_session"] = now.isoformat()
        elif entry["current_interval"] == 2:
            entry["next_run"] = now.isoformat()
        else:
            entry["long_term_review"] = now.isoformat()
        return {"version": "v782_spaced_recall_scheduler", "advanced": lesson_id, "interval": entry["current_interval"], "status": "ok"}
    return {"version": "v782_spaced_recall_scheduler", "scheduled": dict(_spaced_schedule), "status": "ok"}


def main():
    print(f"Nova v782_spaced_recall_scheduler")
    r = spaced_recall_scheduler()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
