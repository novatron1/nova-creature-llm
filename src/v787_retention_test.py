"""v787_retention_test — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def retention_test():
    """Reload saved learning memory and verify retention."""
    approved_path = ROOT / "data/rapid_learning/approved_lessons.jsonl"
    lessons = []
    if approved_path.exists():
        with open(approved_path) as f:
            for line in f:
                line = line.strip()
                if line: lessons.append(json.loads(line))
    passed = [l for l in lessons if l.get("passed", False)]
    return {"version": "v787_retention_test", "total_lessons": len(lessons),
            "retained": len(passed), "retention_rate": len(passed) / max(len(lessons), 1),
            "status": "ok"}


def main():
    print(f"Nova v787_retention_test")
    r = retention_test()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
