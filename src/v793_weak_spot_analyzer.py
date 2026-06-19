"""v793_weak_spot_analyzer — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def weak_spot_analyzer():
    """Analyze weak spots from failed tests."""
    correction_path = ROOT / "data/rapid_learning/correction_queue.jsonl"
    weak = {}
    if correction_path.exists():
        with open(correction_path) as f:
            for line in f:
                line = line.strip()
                if not line: continue
                entry = json.loads(line)
                qtype = entry.get("question_type", "unknown")
                weak[qtype] = weak.get(qtype, 0) + 1
    return {"version": "v793_weak_spot_analyzer", "created_at": datetime.now().isoformat(),
            "weak_spots": weak, "weakest": max(weak, key=weak.get) if weak else "none", "status": "ok"}


def main():
    print(f"Nova v793_weak_spot_analyzer")
    r = weak_spot_analyzer()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
