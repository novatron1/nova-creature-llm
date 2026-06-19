"""v781_correction_loop — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def correction_loop(lesson=None, failed_results=None):
    """Create correction lessons for failed items and retest."""
    if not failed_results:
        return {"version": "v781_correction_loop", "corrections": [], "status": "ok"}
    corrections = []
    for r in failed_results:
        correction = {
            "correction_id": f"cor_{uuid.uuid4().hex[:6]}",
            "lesson_id": r.get("lesson_id", lesson.get("lesson_id") if lesson else "unknown"),
            "original_question": r["question"],
            "mistake_reason": r.get("weakness_reason", "unknown"),
            "correction_lesson": f"Review and correct: {r['question']}",
            "retest_required": True,
            "created_at": datetime.now().isoformat()
        }
        corrections.append(correction)
    return {"version": "v781_correction_loop", "corrections": corrections,
            "correction_count": len(corrections), "status": "ok"}


def main():
    print(f"Nova v781_correction_loop")
    r = correction_loop()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
