"""v777_lesson_chunker — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def lesson_chunker(source="text", content=""):
    """Break teaching input into small atomic lessons."""
    if not content:
        return {"version": "v777_lesson_chunker", "lessons": [], "lesson_count": 0, "status": "ok"}
    sentences = re.split(r'[.!?]+', content)
    lessons = []
    for i, s in enumerate(sentences):
        s = s.strip()
        if len(s) < 10:
            continue
        lesson_id = f"ls_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:4]}"
        words = s.split()
        topic = words[0].lower() if words else "general"
        lessons.append({
            "lesson_id": lesson_id,
            "source": source,
            "topic": topic,
            "claim": s,
            "explanation": "",
            "examples": [],
            "tags": [topic],
            "confidence": 0.7,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        })
    return {"version": "v777_lesson_chunker", "lessons": lessons, "lesson_count": len(lessons), "status": "ok"}


def main():
    print(f"Nova v777_lesson_chunker")
    r = lesson_chunker()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
