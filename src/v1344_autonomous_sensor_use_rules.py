"""vv1344_autonomous_sensor_use_rules — Autonomous Skill Use + Permissioned Will Controller"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def autonomous_sensor_use_rules():
    """Sensors must require permission: camera, mic, screen, speaker, external model/API. Never silently activate sensors."""
    rules = {
        "camera": "requires_permission", "microphone": "requires_permission",
        "screen": "requires_permission", "speaker": "requires_permission",
        "external_model_api": "requires_permission",
        "never_silently_activate": True,
        "must_show_indicator_when_active": True,
    }
    return {"version": "v1344_autonomous_sensor_use_rules", "created_at": datetime.now().isoformat(),
            "module": "Sensors must require permission: camera, mic, screen, speaker, external model/API. Never silently activate sensors.", "sensor_rules": rules, "status": "ok"}


def main():
    print(f"Nova v1344_autonomous_sensor_use_rules")
    r = autonomous_sensor_use_rules()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
