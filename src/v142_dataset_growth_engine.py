"""v142 — Dataset Growth Engine."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "dataset_growth"
REJECTED = {"raw_uncertain_memory","temporary_context","rejected_memory","unapproved_personal"}

def _ensure():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for sub in ["approved","pending","rejected","training_ready"]:
        (DATA_DIR / sub).mkdir(exist_ok=True)

def classify_lesson(text, source, role=None):
    _ensure()
    entry_id = datetime.now().isoformat()
    entry = {"id":entry_id,"text":text[:200],"source":source,"role":role or "unknown",
             "created_at":entry_id}
    # Check for rejected content
    rejection_hints = [r for r in REJECTED if r in text.lower()[:100]]
    if rejection_hints:
        entry["classification"] = "rejected"
        entry["reason"] = f"Hints: {rejection_hints}"
        entry["quality_score"] = 0.0
        entry["training_ready"] = False
    else:
        entry["classification"] = "pending"
        entry["quality_score"] = 0.5
        entry["training_ready"] = False
    return entry

def approve_lesson(entry_id):
    for subdir in DATA_DIR.iterdir():
        if not subdir.is_dir(): continue
        for f in subdir.iterdir():
            if not f.name.endswith(".jsonl"): continue
            with open(f) as fh:
                lines = [json.loads(l) for l in fh if l.strip()]
            for e in lines:
                if e.get("id") == entry_id:
                    e["classification"] = "approved"
                    e["training_ready"] = True
                    e["quality_score"] = min(1.0, e.get("quality_score",0) + 0.3)
                    with open(DATA_DIR/"training_ready"/"approved.jsonl","a") as out:
                        out.write(json.dumps(e)+"\n")
                    return True
    return False

def get_dataset_stats():
    _ensure()
    stats = {"approved":0,"pending":0,"rejected":0,"training_ready":0}
    for subdir in DATA_DIR.iterdir():
        if not subdir.is_dir(): continue
        for f in subdir.iterdir():
            if not f.name.endswith(".jsonl"): continue
            with open(f) as fh:
                count = sum(1 for l in fh if l.strip())
            stats["approved" if "approved" in subdir.name else
                   "rejected" if "rejected" in subdir.name else
                   "training_ready" if "training_ready" in subdir.name else
                   "pending"] += count
    return stats

def main():
    print("Nova v142 -- Dataset Growth Engine\n")
    e = classify_lesson("v086 reasoning core passed all tests", "project_report", "left_hemisphere")
    print(f"Classified: {e['classification']}, quality: {e['quality_score']}")
    stats = get_dataset_stats()
    print(f"Stats: {stats}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
