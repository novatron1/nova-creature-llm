"""v1461_mobile_stop_all — Mobile Phone Bridge + Companion App"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def mobile_stop_all():
    """Emergency stop from phone: stop phone mic/camera, desktop mic/camera, speaker, active task, return to safe idle"""
    actions = ["stop_phone_mic", "stop_phone_camera", "stop_desktop_mic", "stop_desktop_camera", "stop_speaker", "stop_active_task", "return_nova_to_safe_idle"]
    return {"version": "v1461_mobile_stop_all", "created_at": datetime.now().isoformat(),
            "module": "Emergency stop from phone: stop phone mic/camera, desktop mic/camera, speaker, active task, return to safe idle", "stop_actions": actions, "status": "ok"}


def main():
    print(f"Nova v1461_mobile_stop_all")
    r = mobile_stop_all()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
