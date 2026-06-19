"""vv1378_camera_device_discovery — Live Voice + Camera Conversation Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def camera_device_discovery():
    """Create camera scanner: detect available cameras, select default, allow override, save selected, show status, mock test for Codex/cloud"""
    discovered = [
        {"id": "default_camera", "name": "Default Camera", "is_default": True},
        {"id": "mock_camera_1", "name": "Mock Camera 1", "is_default": False},
    ]
    return {"version": "v1378_camera_device_discovery", "created_at": datetime.now().isoformat(),
            "module": "Create camera scanner: detect available cameras, select default, allow override, save selected, show status, mock test for Codex/cloud", "device_type": "camera",
            "devices": discovered, "count": len(discovered),
            "note": "Mock discovery for Codex/cloud. Real device detection requires local hardware runtime.",
            "status": "ok"}


def main():
    print(f"Nova v1378_camera_device_discovery")
    r = camera_device_discovery()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
