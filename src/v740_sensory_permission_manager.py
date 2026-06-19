"""740 — Sensory Body Layer: Sensory Permission Manager"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


_perm_state = {"camera": False, "microphone": False, "speaker_test": False, "screen_capture": False}

def sensory_permission_manager(device=None, grant=None):
    """Manage permission states for all sensory inputs."""
    global _perm_state
    if device and grant is not None:
        _perm_state[device] = grant
        _save_perm_state()
    return {"version": "v740_sensory_permission_manager", "created_at": datetime.now().isoformat(),
            "permissions": dict(_perm_state),
            "all_granted": all(_perm_state.values()),
            "rules": ["no_silent_background_recording", "no_silent_camera_activation", "no_silent_screen_capture"],
            "status": "ok"}

def _save_perm_state():
    p = ROOT / "data/sensory/permissions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_perm_state, indent=2))


def main():
    print(f"Nova v740_sensory_permission_manager")
    r = sensory_permission_manager()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
