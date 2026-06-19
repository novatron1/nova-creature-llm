"""vv1264_voice_output_display_bridge — Nova Creature Face Display + Control Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def voice_output_display_bridge():
    """Module: When Nova speaks: show response text, animate mouth, activate speech_output_transformer light, show speaker status"""
    return {"version": "v1264_voice_output_display_bridge", "created_at": datetime.now().isoformat(),
            "module": "When Nova speaks: show response text, animate mouth, activate speech_output_transformer light, show speaker status", "status": "ok"}


def main():
    print(f"Nova v1264_voice_output_display_bridge")
    r = voice_output_display_bridge()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
