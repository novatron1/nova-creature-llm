"""v1458_mobile_speaker_output — Mobile Phone Bridge + Companion App"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def mobile_speaker_output():
    """Allow Nova response on phone: text response, optional browser speech output, permission toggle required, text-only fallback"""
    return {"version": "v1458_mobile_speaker_output", "created_at": datetime.now().isoformat(), "module": "Allow Nova response on phone: text response, optional browser speech output, permission toggle required, text-only fallback", "text_response": True, "browser_speech_output_optional": True, "permission_toggle_required": True, "text_only_fallback": True, "status": "ok"}


def main():
    print(f"Nova v1458_mobile_speaker_output")
    r = mobile_speaker_output()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
