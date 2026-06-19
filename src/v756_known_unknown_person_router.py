"""v756_known_unknown_person_router — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def known_unknown_person_router(name=None, face_id=None, voice_id=None, is_introduction=False):
    """Route person status: unknown, new, known, or correction."""
    from v754_human_style_recall import human_style_recall
    from v753_auto_people_memory_lock import auto_people_memory_lock
    recall = human_style_recall(name=name, face_id=face_id, voice_id=voice_id)
    status = "unknown_person"
    action = "no_action"
    if recall["confidence"] >= 0.8:
        status = "known_person"
        action = "greet_by_name"
    elif recall["confidence"] >= 0.5:
        status = "possible_match"
        action = "ask_confirmation"
    elif recall["matches"] and recall["confidence"] < 0.5:
        status = "low_confidence_match"
        action = "ask_naturally"
    elif is_introduction and name:
        status = "new_introduction"
        action = "auto_create_profile"
    return {"version": "v756_known_unknown_person_router", "created_at": datetime.now().isoformat(),
            "person_status": status, "action": action, "confidence": recall.get("confidence", 0.0),
            "recall": recall.get("recall", ""), "status": "ok"}


def main():
    import sys
    print(f"Nova v756_known_unknown_person_router")
    r = known_unknown_person_router()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
