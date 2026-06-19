"""v774_people_memory_maintenance — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def people_memory_maintenance(action="status"):
    """Maintenance tasks for people memory system."""
    now = datetime.now().isoformat()
    from v751_people_memory_database import people_memory_database
    from v762_profile_merge_detector import profile_merge_detector
    db = people_memory_database()
    profiles = db.get("profiles", [])
    result = {"version": "v774_people_memory_maintenance", "created_at": now, "status": "ok"}
    if action == "status":
        result["total_profiles"] = len(profiles)
        result["active_profiles"] = len([p for p in profiles if p.get("profile_status") not in ("forgotten",)])
        result["merge_candidates"] = profile_merge_detector().get("candidate_count", 0)
    elif action == "cleanup":
        active = [p for p in profiles if p.get("profile_status") != "forgotten"]
        db_path = ROOT / "data/people/profiles.jsonl"
        with open(db_path, "w") as f:
            for p in active:
                f.write(json.dumps(p) + "\n")
        result["removed"] = len(profiles) - len(active)
        result["remaining"] = len(active)
    elif action == "stats":
        result["total"] = len(profiles)
        result["by_status"] = {}
        for p in profiles:
            s = p.get("profile_status", "unknown")
            result["by_status"][s] = result["by_status"].get(s, 0) + 1
    return result


def main():
    import sys
    print(f"Nova v774_people_memory_maintenance")
    r = people_memory_maintenance()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
