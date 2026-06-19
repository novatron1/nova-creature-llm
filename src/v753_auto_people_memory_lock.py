"""v753_auto_people_memory_lock — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def auto_people_memory_lock(text="", context=None):
    """Auto-create person profile on introduction trigger. No owner confirmation needed."""
    if not text:
        return {"version": "v753_auto_people_memory_lock", "status": "no_input"}
    from v751_people_memory_database import people_memory_database
    from v752_introduction_trigger_parser import introduction_trigger_parser
    detections = introduction_trigger_parser(text)
    results = []
    for d in detections.get("detections", []):
        profile = {
            "display_name": d["display_name"],
            "claimed_name": d["display_name"],
            "name_source": d["source"],
            "relationship": d.get("relationship", ""),
            "introduction_text": d.get("original_phrase", text),
            "introduction_context": context or "conversation",
            "face_embedding_id": "",
            "voice_embedding_id": "",
            "face_confidence": 0.0,
            "voice_confidence": 0.0,
            "notes": f"Auto-created from {d['source']}",
            "trust_level": 0.5
        }
        r = people_memory_database(profile=profile)
        r["trigger_source"] = d["source"]
        r["auto_created"] = True
        r["owner_confirmation_required"] = False
        results.append(r)
    return {"version": "v753_auto_people_memory_lock", "created_at": datetime.now().isoformat(),
            "profiles_created": len(results), "results": results,
            "owner_confirmation_required": False, "status": "ok"}


def main():
    import sys
    print(f"Nova v753_auto_people_memory_lock")
    r = auto_people_memory_lock()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
