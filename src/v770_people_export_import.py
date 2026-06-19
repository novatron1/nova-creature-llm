"""v770_people_export_import — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def people_export_import(action="export", data=None):
    """Export or import people profiles as JSON."""
    from v751_people_memory_database import people_memory_database
    export_path = ROOT / "exports/v770_people_export"
    export_path.mkdir(parents=True, exist_ok=True)
    if action == "export":
        db = people_memory_database()
        profiles = db.get("profiles", [])
        path = export_path / f"people_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(profiles, indent=2))
        return {"version": "v770_people_export_import", "exported": len(profiles), "path": str(path), "status": "ok"}
    elif action == "import":
        if not data: return {"version": "v770_people_export_import", "action": "import", "status": "no_data"}
        from v751_people_memory_database import people_memory_database
        count = 0
        for profile in data:
            people_memory_database(profile=profile)
            count += 1
        return {"version": "v770_people_export_import", "imported": count, "status": "ok"}
    return {"version": "v770_people_export_import", "status": "unknown_action"}


def main():
    import sys
    print(f"Nova v770_people_export_import")
    r = people_export_import()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
