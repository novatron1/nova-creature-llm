"""v796_teach_speed_optimizer — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def teach_speed_optimizer(lesson_count=0, time_spent_minutes=0):
    """Optimize teaching speed based on lesson throughput."""
    speed = lesson_count / max(time_spent_minutes, 1)
    rating = "fast" if speed > 5 else "moderate" if speed > 2 else "slow"
    return {"version": "v796_teach_speed_optimizer", "lessons_per_minute": round(speed, 2),
            "rating": rating, "recommendation": "Increase batch size" if rating == "slow" else "Maintain current pace",
            "status": "ok"}


def main():
    print(f"Nova v796_teach_speed_optimizer")
    r = teach_speed_optimizer()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
