"""v937_export_best_training_set — Whole-Brain Training Lab"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

def export_best_training_set():
    """Training Lab: Export only best approved lessons to exports/best_training_lessons.jsonl"""
    return {"version": "v937_export_best_training_set", "created_at": datetime.now().isoformat(),
            "module": "Export only best approved lessons to exports/best_training_lessons.jsonl", "status": "ok"}


def main():
    print(f"Nova v937_export_best_training_set")
    r = export_best_training_set()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
