"""v1462_mobile_permission_gate — Mobile Phone Bridge + Companion App"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def mobile_permission_gate():
    """Rules: no phone mic/camera without permission, no speaker unless enabled, no sensor logging in private mode, no permanent people memory unless allowed"""
    rules = {
        "phone_mic": "requires_permission", "phone_camera": "requires_permission",
        "speaker_output": "requires_enable", "sensor_logging_in_private_mode": "blocked",
        "permanent_people_memory_unless_allowed": True,
    }
    return {"version": "v1462_mobile_permission_gate", "created_at": datetime.now().isoformat(),
            "module": "Rules: no phone mic/camera without permission, no speaker unless enabled, no sensor logging in private mode, no permanent people memory unless allowed", "permission_rules": rules, "status": "ok"}


def main():
    print(f"Nova v1462_mobile_permission_gate")
    r = mobile_permission_gate()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
