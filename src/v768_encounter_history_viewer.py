"""v768_encounter_history_viewer — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def encounter_history_viewer(person_id=None):
    """View encounter history for a person."""
    from v751_people_memory_database import people_memory_database
    db = people_memory_database()
    profiles = db.get("profiles", [])
    if person_id:
        profiles = [p for p in profiles if p.get("person_id") == person_id]
    results = []
    for p in profiles:
        results.append({"person_id": p["person_id"], "display_name": p["display_name"],
                        "first_seen": p.get("first_seen"), "last_seen": p.get("last_seen"),
                        "times_seen": p.get("times_seen", 0),
                        "encounter_history": p.get("encounter_history", [])[-10:]})
    return {"version": "v768_encounter_history_viewer", "created_at": datetime.now().isoformat(),
            "histories": results, "status": "ok"}


def main():
    import sys
    print(f"Nova v768_encounter_history_viewer")
    r = encounter_history_viewer()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
