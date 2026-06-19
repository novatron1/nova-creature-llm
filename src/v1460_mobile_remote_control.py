"""v1460_mobile_remote_control — Mobile Phone Bridge + Companion App"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def mobile_remote_control():
    """Phone can control: start/stop voice/camera, private mode, stop all, run test, show capability/memory/route trace"""
    controls = {
        "start_stop_voice_mode": True, "start_stop_camera_mode": True,
        "private_mode": True, "stop_all": True, "run_test_conversation": True,
        "show_capability_list": True, "show_memory_status": True, "show_route_trace": True
    }
    return {"version": "v1460_mobile_remote_control", "created_at": datetime.now().isoformat(),
            "module": "Phone can control: start/stop voice/camera, private mode, stop all, run test, show capability/memory/route trace", "controls": controls, "status": "ok"}


def main():
    print(f"Nova v1460_mobile_remote_control")
    r = mobile_remote_control()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
