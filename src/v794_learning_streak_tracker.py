"""v794_learning_streak_tracker — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


_learning_streak = {"current": 0, "best": 0, "last_date": None}

def learning_streak_tracker(action="status", learned_today=False):
    """Track learning streak over days."""
    from datetime import date
    global _learning_streak
    today = date.today().isoformat()
    if action == "record" and learned_today:
        if _learning_streak["last_date"] == today:
            pass  # already counted today
        elif _learning_streak["last_date"] is not None:
            from datetime import timedelta
            last = date.fromisoformat(_learning_streak["last_date"])
            if (date.today() - last).days <= 1:
                _learning_streak["current"] += 1
            else:
                _learning_streak["current"] = 1
        else:
            _learning_streak["current"] = 1
        _learning_streak["best"] = max(_learning_streak["best"], _learning_streak["current"])
        _learning_streak["last_date"] = today
    return {"version": "v794_learning_streak_tracker", "streak": dict(_learning_streak), "status": "ok"}


def main():
    print(f"Nova v794_learning_streak_tracker")
    r = learning_streak_tracker()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
