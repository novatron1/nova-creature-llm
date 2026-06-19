"""v762_profile_merge_detector — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def profile_merge_detector():
    """Detect potential duplicate profiles that should be merged."""
    db_path = ROOT / "data/people/profiles.jsonl"
    profiles = []
    if db_path.exists():
        with open(db_path) as f:
            for line in f:
                line = line.strip()
                if line: profiles.append(json.loads(line))
    merges = []
    for i, a in enumerate(profiles):
        for j, b in enumerate(profiles):
            if i >= j: continue
            if a.get("display_name", "").lower() == b.get("display_name", "").lower():
                merges.append({"profile_a": a["person_id"], "profile_b": b["person_id"],
                               "name": a["display_name"], "reason": "same_name", "confidence": 0.9})
            elif a.get("face_embedding_id") and a.get("face_embedding_id") == b.get("face_embedding_id"):
                merges.append({"profile_a": a["person_id"], "profile_b": b["person_id"],
                               "name": f"{a['display_name']}/{b['display_name']}", "reason": "same_face", "confidence": 0.85})
    return {"version": "v762_profile_merge_detector", "created_at": datetime.now().isoformat(),
            "merge_candidates": merges, "candidate_count": len(merges), "status": "ok"}


def main():
    import sys
    print(f"Nova v762_profile_merge_detector")
    r = profile_merge_detector()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
