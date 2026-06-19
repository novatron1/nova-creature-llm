"""v769_people_search_engine — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def people_search_engine(query=""):
    """Search people memory by name, relationship, or notes."""
    from v751_people_memory_database import people_memory_database
    db = people_memory_database()
    profiles = db.get("profiles", [])
    q = query.lower()
    results = []
    for p in profiles:
        if q in p.get("display_name", "").lower() or q in p.get("relationship", "").lower() or q in p.get("notes", "").lower():
            results.append({"person_id": p["person_id"], "display_name": p["display_name"],
                            "relationship": p.get("relationship"), "status": p.get("profile_status")})
    return {"version": "v769_people_search_engine", "created_at": datetime.now().isoformat(),
            "query": query, "results": results, "count": len(results), "status": "ok"}


def main():
    import sys
    print(f"Nova v769_people_search_engine")
    r = people_search_engine()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
