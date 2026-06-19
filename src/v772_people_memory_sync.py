"""v772_people_memory_sync — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def people_memory_sync():
    """Sync people memory profiles to data store."""
    from v751_people_memory_database import people_memory_database
    db = people_memory_database()
    sync_path = ROOT / "data/people/sync"
    sync_path.mkdir(parents=True, exist_ok=True)
    profiles = db.get("profiles", [])
    sync_file = sync_path / f"sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    sync_file.write_text(json.dumps(profiles, indent=2))
    return {"version": "v772_people_memory_sync", "synced_at": datetime.now().isoformat(),
            "profile_count": len(profiles), "path": str(sync_file), "status": "ok"}


def main():
    import sys
    print(f"Nova v772_people_memory_sync")
    r = people_memory_sync()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
