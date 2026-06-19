"""704 — Sensory Body Layer: Permission Gate"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


PERMISSIONS = {"camera": None, "microphone": None, "speaker_test": None, "screen_capture": None}

def permission_gate(device_type=None, grant=None):
    """Explicit permission gate. No silent activation."""
    global PERMISSIONS
    if device_type and grant is not None:
        PERMISSIONS[device_type] = grant
        _save_permissions()
    return {"version": "v704_permission_gate", "created_at": datetime.now().isoformat(),
            "permissions": dict(PERMISSIONS),
            "rules": ["no_silent_background_recording", "no_silent_camera_activation", "no_silent_screen_capture"],
            "status": "ok"}

def _save_permissions():
    p = ROOT / "data/sensory/permissions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(PERMISSIONS, indent=2))

def check_permission(device_type):
    return PERMISSIONS.get(device_type, False)


def main():
    print(f"Nova v704_permission_gate")
    r = permission_gate()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
