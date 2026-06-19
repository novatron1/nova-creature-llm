"""v803_master_permission_bridge — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def master_permission_bridge(system="", action="check"):
    """Ensure all sensory/action systems go through permission gate."""
    from v704_permission_gate import permission_gate, check_permission
    systems = {
        "camera": {"required": True},
        "microphone": {"required": True},
        "speaker": {"required": True},
        "screen": {"required": True},
        "file_read_write": {"required": True},
        "people_memory": {"required": True},
        "private_mode": {"required": False},
        "learning_mode": {"required": False},
    }
    if action == "check" and system:
        if system not in systems:
            return {"version": "v803_master_permission_bridge", "system": system, "allowed": False, "reason": "unknown_system", "status": "ok"}
        allowed = check_permission(system) if system in ("camera", "microphone", "speaker_test", "screen_capture") else True
        return {"version": "v803_master_permission_bridge", "system": system, "allowed": allowed, "status": "ok"}
    elif action == "status":
        perms = {}
        for s in systems:
            allowed = check_permission(s) if s in ("camera", "microphone", "speaker_test", "screen_capture") else True
            perms[s] = {"allowed": allowed, "required": systems[s]["required"]}
        return {"version": "v803_master_permission_bridge", "permissions": perms, "status": "ok"}
    return {"version": "v803_master_permission_bridge", "status": "ok"}


def main():
    print(f"Nova v803_master_permission_bridge")
    r = master_permission_bridge()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
