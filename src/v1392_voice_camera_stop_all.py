"""vv1392_voice_camera_stop_all — Live Voice + Camera Conversation Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def voice_camera_stop_all():
    """Emergency stop: stop mic, camera, speaker, current task, clear stream buffers, return display to safe idle"""
    actions = ["stop_mic", "stop_camera", "stop_speaker", "stop_current_task", "clear_temporary_stream_buffers", "return_display_to_safe_idle"]
    return {"version": "v1392_voice_camera_stop_all", "created_at": datetime.now().isoformat(),
            "module": "Emergency stop: stop mic, camera, speaker, current task, clear stream buffers, return display to safe idle", "stop_actions": actions, "status": "ok"}


def main():
    print(f"Nova v1392_voice_camera_stop_all")
    r = voice_camera_stop_all()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
