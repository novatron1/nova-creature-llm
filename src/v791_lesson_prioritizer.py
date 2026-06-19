"""v791_lesson_prioritizer — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def lesson_prioritizer(lessons=None):
    """Prioritize lessons by confidence and importance."""
    if not lessons:
        return {"version": "v791_lesson_prioritizer", "prioritized": [], "status": "ok"}
    scored = []
    for l in lessons:
        conf = l.get("confidence", 0.5)
        score = conf * (1.0 if l.get("source") == "user_correction" else 0.8)
        scored.append((score, l))
    scored.sort(key=lambda x: x[0], reverse=True)
    return {"version": "v791_lesson_prioritizer", "prioritized": [s[1] for s in scored], "count": len(scored), "status": "ok"}


def main():
    print(f"Nova v791_lesson_prioritizer")
    r = lesson_prioritizer()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
