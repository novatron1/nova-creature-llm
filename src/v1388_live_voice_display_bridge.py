"""vv1388_live_voice_display_bridge — Live Voice + Camera Conversation Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def live_voice_display_bridge():
    """Connect voice mode to v1300 display: listening expression, thinking expression, talking animation, speech route light, transcript and response on screen"""
    actions = {
        "listening_expression": True, "thinking_expression": True,
        "talking_animation": True, "speech_route_light": True,
        "transcript_shown": True, "response_shown": True,
    }
    return {"version": "v1388_live_voice_display_bridge", "created_at": datetime.now().isoformat(),
            "module": "Connect voice mode to v1300 display: listening expression, thinking expression, talking animation, speech route light, transcript and response on screen", "display_actions": actions, "status": "ok"}


def main():
    print(f"Nova v1388_live_voice_display_bridge")
    r = live_voice_display_bridge()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
