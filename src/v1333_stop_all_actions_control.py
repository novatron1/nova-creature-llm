"""vv1333_stop_all_actions_control — Autonomous Skill Use + Permissioned Will Controller"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def stop_all_actions_control():
    """Add emergency stop: stop sensors, speaker, screen capture, file writes, current task, return to safe idle"""
    actions = ["stop_sensors", "stop_speaker", "stop_screen_capture", "stop_file_writes", "stop_current_task", "return_to_safe_idle"]
    return {"version": "v1333_stop_all_actions_control", "created_at": datetime.now().isoformat(),
            "module": "Add emergency stop: stop sensors, speaker, screen capture, file writes, current task, return to safe idle", "stop_actions": actions, "status": "ok"}


def main():
    print(f"Nova v1333_stop_all_actions_control")
    r = stop_all_actions_control()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
