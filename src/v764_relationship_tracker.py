"""v764_relationship_tracker — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]

def relationship_tracker(person_id=None, relationship=None):
    """Track relationships with people over time."""
    rel_path = ROOT / "data/people/relationships.jsonl"
    rel_path.parent.mkdir(parents=True, exist_ok=True)
    if person_id and relationship:
        entry = {"person_id": person_id, "relationship": relationship, "updated_at": datetime.now().isoformat()}
        with open(rel_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"version": "v764_relationship_tracker", "updated": entry, "status": "ok"}
    rels = []
    if rel_path.exists():
        with open(rel_path) as f:
            for line in f:
                line = line.strip()
                if line: rels.append(json.loads(line))
    return {"version": "v764_relationship_tracker", "relationships": rels, "status": "ok"}


def main():
    import sys
    print(f"Nova v764_relationship_tracker")
    r = relationship_tracker()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
