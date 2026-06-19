"""v751_people_memory_database — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]

def people_memory_database(person_id=None, profile=None):
    """People memory database with full profile fields."""
    db_path = ROOT / "data/people/profiles.jsonl"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if profile:
        now = datetime.now().isoformat()
        entry = {
            "person_id": person_id or str(uuid.uuid4())[:8],
            "display_name": profile.get("display_name", "Unknown"),
            "claimed_name": profile.get("claimed_name", ""),
            "name_source": profile.get("name_source", "self_introduction"),
            "profile_status": "new",
            "relationship": profile.get("relationship", ""),
            "first_seen": now,
            "last_seen": now,
            "times_seen": 1,
            "face_embedding_id": profile.get("face_embedding_id", ""),
            "voice_embedding_id": profile.get("voice_embedding_id", ""),
            "face_confidence": profile.get("face_confidence", 0.0),
            "voice_confidence": profile.get("voice_confidence", 0.0),
            "introduction_text": profile.get("introduction_text", ""),
            "introduction_context": profile.get("introduction_context", ""),
            "encounter_history": profile.get("encounter_history", []),
            "notes": profile.get("notes", ""),
            "trust_level": profile.get("trust_level", 0.5),
            "correction_history": profile.get("correction_history", []),
            "created_at": now
        }
        entry["profile_status"] = "known_by_introduction" if profile.get("name_source") != "owner_label" else "new"
        with open(db_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"version": "v751_people_memory_database", "created_at": now,
                "person_id": entry["person_id"], "profile": entry, "status": "ok"}
    # List profiles
    profiles = []
    if db_path.exists():
        with open(db_path) as f:
            for line in f:
                line = line.strip()
                if line: profiles.append(json.loads(line))
    return {"version": "v751_people_memory_database", "created_at": datetime.now().isoformat(),
            "total_profiles": len(profiles), "profiles": profiles, "status": "ok"}


def main():
    import sys
    print(f"Nova v751_people_memory_database")
    r = people_memory_database()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
