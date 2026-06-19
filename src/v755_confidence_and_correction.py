"""v755_confidence_and_correction — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def confidence_and_correction(action=None, person_id=None, current_name=None, corrected_name=None):
    """Allow natural correction of person profiles."""
    db_path = ROOT / "data/people/profiles.jsonl"
    now = datetime.now().isoformat()
    result = {"version": "v755_confidence_and_correction", "created_at": now, "status": "ok"}
    if action == "correct_name":
        new_profiles = []
        corrected = False
        if db_path.exists():
            with open(db_path) as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    p = json.loads(line)
                    if person_id and p.get("person_id") == person_id:
                        p["correction_history"] = p.get("correction_history", []) + [{"from": p["display_name"], "to": corrected_name, "at": now}]
                        p["display_name"] = corrected_name
                        p["profile_status"] = "corrected"
                        corrected = True
                    new_profiles.append(p)
        if corrected:
            with open(db_path, "w") as f:
                for p in new_profiles:
                    f.write(json.dumps(p) + "\n")
            result["correction"] = f"Name corrected from {current_name} to {corrected_name}"
        else:
            result["correction"] = "Person not found"
    elif action == "suggest_merge":
        result["merge_suggestion"] = "Two profiles may be the same person. Use merge_profiles to combine."
    elif action == "low_confidence":
        result["response"] = "I might be mixing this up."
    return result


def main():
    import sys
    print(f"Nova v755_confidence_and_correction")
    r = confidence_and_correction()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
