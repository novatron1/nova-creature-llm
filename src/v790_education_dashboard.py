"""v790_education_dashboard — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def education_dashboard():
    """Dashboard showing rapid learning stats."""
    intake_path = ROOT / "data/rapid_learning/intake_log.jsonl"
    approved_path = ROOT / "data/rapid_learning/approved_lessons.jsonl"
    correction_path = ROOT / "data/rapid_learning/correction_queue.jsonl"
    intake_count = 0
    if intake_path.exists():
        with open(intake_path) as f:
            intake_count = sum(1 for _ in f)
    approved = []
    if approved_path.exists():
        with open(approved_path) as f:
            for line in f:
                line = line.strip()
                if line: approved.append(json.loads(line))
    corrections = []
    if correction_path.exists():
        with open(correction_path) as f:
            for line in f:
                line = line.strip()
                if line: corrections.append(json.loads(line))
    passed = [a for a in approved if a.get("passed")]
    failed = [a for a in approved if not a.get("passed")]
    return {"version": "v790_education_dashboard", "created_at": datetime.now().isoformat(),
            "stats": {
                "lessons_received": intake_count,
                "lessons_chunked": len(approved) + len(corrections),
                "questions_generated": len(approved) + len(corrections) * 4,
                "tests_passed": len(passed),
                "tests_failed": len(failed),
                "corrections_created": len(corrections),
                "approved_lessons": len(passed),
                "pending_lessons": len(corrections),
                "weak_topics": ["unknown"],
                "strongest_topics": ["general"]
            }, "status": "ok"}


def main():
    print(f"Nova v790_education_dashboard")
    r = education_dashboard()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
