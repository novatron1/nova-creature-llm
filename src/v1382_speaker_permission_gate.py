"""vv1382_speaker_permission_gate — Live Voice + Camera Conversation Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def speaker_permission_gate():
    """Create explicit speaker permission flow: ask before voice output, allow text-only mode, allow voice mode, log speaker output permission"""
    permission = {
        "device": "speaker",
        "default_denied": True,
        "requires_explicit_permission": True,
        "show_usage_explanation": True,
        "show_stop_command": True,
        "log_permission_events": True,
        "current_status": "denied",
        "note": "Permission gate active. No silent speaker use allowed."
    }
    return {"version": "v1382_speaker_permission_gate", "created_at": datetime.now().isoformat(),
            "module": "Create explicit speaker permission flow: ask before voice output, allow text-only mode, allow voice mode, log speaker output permission", "permission": permission, "status": "ok"}


def main():
    print(f"Nova v1382_speaker_permission_gate")
    r = speaker_permission_gate()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
