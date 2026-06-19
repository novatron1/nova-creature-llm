"""v799_mastery_checker — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def mastery_checker(topic="", lessons=None):
    """Check if a topic has been mastered."""
    if not lessons:
        return {"version": "v799_mastery_checker", "mastered": False, "status": "no_data"}
    topic_lessons = [l for l in lessons if l.get("topic", "").lower() == topic.lower()]
    if not topic_lessons:
        return {"version": "v799_mastery_checker", "topic": topic, "mastered": False, "reason": "no_lessons", "status": "ok"}
    passed = [l for l in topic_lessons if l.get("passed", False)]
    rate = len(passed) / max(len(topic_lessons), 1)
    mastered = rate >= 0.8
    return {"version": "v799_mastery_checker", "topic": topic, "mastered": mastered,
            "total_lessons": len(topic_lessons), "passed": len(passed), "rate": round(rate, 2), "status": "ok"}


def main():
    print(f"Nova v799_mastery_checker")
    r = mastery_checker()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
