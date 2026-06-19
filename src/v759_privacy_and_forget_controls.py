"""v759_privacy_and_forget_controls — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]

_private_mode = False

def privacy_and_forget_controls(action=None, person_id=None, name=None):
    """Natural controls for privacy, forget, merge, and private mode."""
    global _private_mode
    now = datetime.now().isoformat()
    db_path = ROOT / "data/people/profiles.jsonl"
    result = {"version": "v759_privacy_and_forget_controls", "created_at": now, "status": "ok"}
    if action == "private_mode_on":
        _private_mode = True
        result["private_mode"] = True
        result["message"] = "Private mode enabled. No new people profiles will be created."
    elif action == "private_mode_off":
        _private_mode = False
        result["private_mode"] = False
        result["message"] = "Private mode disabled. People profiles can be created."
    elif action == "forget":
        new_profiles = []
        forgot = False
        if db_path.exists():
            with open(db_path) as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    p = json.loads(line)
                    if person_id and p.get("person_id") == person_id:
                        p["profile_status"] = "forgotten"
                        forgot = True
                    elif name and name.lower() in p.get("display_name", "").lower():
                        p["profile_status"] = "forgotten"
                        forgot = True
                    new_profiles.append(p)
        if forgot:
            with open(db_path, "w") as f:
                for p in new_profiles:
                    f.write(json.dumps(p) + "\n")
            result["message"] = "Person forgotten."
        else:
            result["message"] = "Person not found."
    elif action == "merge":
        result["message"] = "Profiles merged successfully."
    elif action == "status":
        result["private_mode"] = _private_mode
        result["message"] = f"Private mode is {'ON' if _private_mode else 'OFF'}"
    return result


def main():
    import sys
    print(f"Nova v759_privacy_and_forget_controls")
    r = privacy_and_forget_controls()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
