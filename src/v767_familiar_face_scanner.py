"""v767_familiar_face_scanner — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def familiar_face_scanner(face_data=None):
    """Scan face against known people and return match."""
    from v761_face_print_profile import face_print_profile
    from v754_human_style_recall import human_style_recall
    if face_data:
        return human_style_recall(face_id=face_data)
    return {"version": "v767_familiar_face_scanner", "created_at": datetime.now().isoformat(),
            "scan_active": False, "status": "ok"}


def main():
    import sys
    print(f"Nova v767_familiar_face_scanner")
    r = familiar_face_scanner()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
