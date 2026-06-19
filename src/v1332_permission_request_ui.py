"""vv1332_permission_request_ui — Autonomous Skill Use + Permissioned Will Controller"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def permission_request_ui():
    """When permission is needed, ask clearly: what skill, why, what it will do, how long, how to stop it"""
    permission_dialog = {
        "title": "Nova needs permission",
        "fields": ["skill_name", "reason", "what_it_will_do", "how_long", "how_to_stop"],
        "buttons": ["allow_once", "allow_always", "deny"],
        "example": {"skill": "camera", "reason": "You asked me to see who is there", "what_it_will_do": "Activate camera and detect faces", "how_long": "Until you say stop or task ends", "how_to_stop": "Say 'stop camera' or click Stop All"},
    }
    return {"version": "v1332_permission_request_ui", "created_at": datetime.now().isoformat(),
            "module": "When permission is needed, ask clearly: what skill, why, what it will do, how long, how to stop it", "permission_dialog": permission_dialog, "status": "ok"}


def main():
    print(f"Nova v1332_permission_request_ui")
    r = permission_request_ui()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
