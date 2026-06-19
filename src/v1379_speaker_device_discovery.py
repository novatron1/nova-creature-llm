"""vv1379_speaker_device_discovery — Live Voice + Camera Conversation Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def speaker_device_discovery():
    """Create speaker/output scanner: detect output device when possible, default speaker output, test phrase button, mock speaker test for Codex/cloud"""
    discovered = [
        {"id": "default_speaker", "name": "Default Speaker", "is_default": True},
        {"id": "mock_speaker_1", "name": "Mock Speaker 1", "is_default": False},
    ]
    return {"version": "v1379_speaker_device_discovery", "created_at": datetime.now().isoformat(),
            "module": "Create speaker/output scanner: detect output device when possible, default speaker output, test phrase button, mock speaker test for Codex/cloud", "device_type": "speaker",
            "devices": discovered, "count": len(discovered),
            "note": "Mock discovery for Codex/cloud. Real device detection requires local hardware runtime.",
            "status": "ok"}


def main():
    print(f"Nova v1379_speaker_device_discovery")
    r = speaker_device_discovery()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
