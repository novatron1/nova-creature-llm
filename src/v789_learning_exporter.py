"""v789_learning_exporter — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def learning_exporter():
    """Export approved lessons to training sets."""
    approved_path = ROOT / "data/rapid_learning/approved_lessons.jsonl"
    export_dir = ROOT / "exports/rapid_learning_training_set"
    export_dir.mkdir(parents=True, exist_ok=True)
    train_dir = ROOT / "training_data/rapid_learning"
    train_dir.mkdir(parents=True, exist_ok=True)
    lessons = []
    if approved_path.exists():
        with open(approved_path) as f:
            for line in f:
                line = line.strip()
                if line: lessons.append(json.loads(line))
    ts_path = export_dir / "rapid_learning_training_set.json"
    ts_path.write_text(json.dumps(lessons, indent=2))
    al_path = train_dir / "approved_lessons.jsonl"
    with open(al_path, "w") as f:
        for l in lessons:
            f.write(json.dumps(l) + "\n")
    summary = {"exported_at": datetime.now().isoformat(), "lesson_count": len(lessons),
               "training_set": str(ts_path), "approved_path": str(al_path)}
    summary_path = ROOT / "reports/rapid_learning_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    return {"version": "v789_learning_exporter", "exported": len(lessons),
            "training_set_path": str(ts_path), "summary": summary, "status": "ok"}


def main():
    print(f"Nova v789_learning_exporter")
    r = learning_exporter()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
