"""vv1399_voice_camera_run_guide — Live Voice + Camera Conversation Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def voice_camera_run_guide():
    """Create run guide explaining how to run terminal/display mode, enable mic/camera/speaker, stop all, private mode, where logs save, mock vs real distinction"""
    guide = {
        "how_to_run_terminal_mode": "python src/v1395_live_voice_camera_terminal.py",
        "how_to_open_display_mode": "Open src/v1396_live_voice_camera_display.html in browser",
        "how_to_enable_mic": "Type: allow mic",
        "how_to_enable_camera": "Type: allow camera",
        "how_to_enable_speaker": "Type: allow speaker",
        "how_to_stop_all": "Type: stop all",
        "how_private_mode_works": "Toggle private mode to block permanent memory and sensor logging",
        "where_logs_save": "voice_camera_runtime/transcripts/",
        "mock_vs_real": "Codex/cloud runs in mock mode. Real mic/camera/speaker requires local hardware runtime with permissions.",
    }
    guide_path = ROOT / "reports" / "v1399_voice_camera_run_guide.md"
    os.makedirs(str(guide_path.parent), exist_ok=True)
    with open(guide_path, "w") as f:
        json.dump(guide, f, indent=2)
    return {"version": "v1399_voice_camera_run_guide", "created_at": datetime.now().isoformat(),
            "module": "Create run guide explaining how to run terminal/display mode, enable mic/camera/speaker, stop all, private mode, where logs save, mock vs real distinction", "guide": guide, "status": "ok"}


def main():
    print(f"Nova v1399_voice_camera_run_guide")
    r = voice_camera_run_guide()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
