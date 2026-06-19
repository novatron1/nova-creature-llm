"""v780_rapid_learning_memory_lock — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def rapid_learning_memory_lock(test_result=None):
    """Save passed lessons, queue failed ones."""
    if not test_result:
        return {"version": "v780_rapid_learning_memory_lock", "approved": 0, "queued": 0, "status": "ok"}
    approved_path = ROOT / "data/rapid_learning/approved_lessons.jsonl"
    correction_path = ROOT / "data/rapid_learning/correction_queue.jsonl"
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat()
    a_count = 0
    c_count = 0
    for r in test_result.get("results", []):
        entry = {"lesson_id": test_result.get("lesson_id"), "question_type": r["question_type"],
                 "question": r["question"], "score": r["score"], "passed": r["passed"],
                 "timestamp": now}
        if r["passed"]:
            with open(approved_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
            a_count += 1
        else:
            with open(correction_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
            c_count += 1
    return {"version": "v780_rapid_learning_memory_lock", "approved_count": a_count,
            "correction_count": c_count, "status": "ok"}


def main():
    print(f"Nova v780_rapid_learning_memory_lock")
    r = rapid_learning_memory_lock()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
