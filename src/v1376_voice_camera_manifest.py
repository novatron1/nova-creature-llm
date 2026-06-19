"""vv1376_voice_camera_manifest — Live Voice + Camera Conversation Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def voice_camera_manifest():
    """Create manifest, folders, tests, reports, and runtime registry for live mic/camera conversation"""
    os.makedirs(str(ROOT / "voice_camera_runtime"), exist_ok=True)
    os.makedirs(str(ROOT / "voice_camera_runtime" / "transcripts"), exist_ok=True)
    os.makedirs(str(ROOT / "voice_camera_runtime" / "snapshots"), exist_ok=True)
    os.makedirs(str(ROOT / "voice_camera_runtime" / "reports"), exist_ok=True)
    manifest = {
        "version": "v1376_voice_camera_manifest",
        "created_at": datetime.now().isoformat(),
        "module": "Create manifest, folders, tests, reports, and runtime registry for live mic/camera conversation",
        "devices": ["microphone", "camera", "speaker"],
        "permissions": ["mic_permission", "camera_permission", "speaker_permission"],
        "runtimes": ["terminal_mock", "display_mock", "local_live_placeholder"],
        "folders": ["transcripts", "snapshots", "reports"],
        "status": "ok"
    }
    manifest_path = ROOT / "voice_camera_runtime" / "voice_camera_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main():
    print(f"Nova v1376_voice_camera_manifest")
    r = voice_camera_manifest()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
