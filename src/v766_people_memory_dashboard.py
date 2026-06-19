"""v766_people_memory_dashboard — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def people_memory_dashboard():
    """Dashboard showing people memory status."""
    from v751_people_memory_database import people_memory_database
    db = people_memory_database()
    profiles = db.get("profiles", [])
    stats = {"total_people": len(profiles), "known": 0, "new": 0, "forgotten": 0, "corrected": 0}
    for p in profiles:
        s = p.get("profile_status", "new")
        if s in stats: stats[s] += 1
        else: stats["new"] += 1
    return {"version": "v766_people_memory_dashboard", "created_at": datetime.now().isoformat(),
            "stats": stats, "recent_profiles": profiles[-10:], "status": "ok"}


def main():
    import sys
    print(f"Nova v766_people_memory_dashboard")
    r = people_memory_dashboard()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
