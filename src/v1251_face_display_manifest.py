"""vv1251_face_display_manifest — Nova Creature Face Display + Control Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def face_display_manifest():
    """Module: Create the manifest, folders, reports, UI registry, and test registry for the live display runtime"""
    os.makedirs(str(ROOT / "face_display"), exist_ok=True)
    os.makedirs(str(ROOT / "face_display" / "themes"), exist_ok=True)
    os.makedirs(str(ROOT / "face_display" / "expressions"), exist_ok=True)
    os.makedirs(str(ROOT / "face_display" / "assets"), exist_ok=True)
    os.makedirs(str(ROOT / "face_display" / "reports"), exist_ok=True)
    manifest = {
        "version": "v1251_face_display_manifest",
        "created_at": datetime.now().isoformat(),
        "module": "Create the manifest, folders, reports, UI registry, and test registry for the live display runtime",
        "display_modes": ["face", "chat", "sensory", "learning", "coding", "creative", "private", "standby"],
        "expressions": ["neutral", "happy", "focused", "thinking", "surprised", "confused", "listening", "talking", "learning", "error", "sleep"],
        "brain_roles": ["left_hemisphere", "right_hemisphere", "memory_transformer", "planner_transformer", "critic_conscience_transformer", "dream_simulation_transformer", "speech_output_transformer"],
        "panels": ["sensory", "learning_memory", "chat_command", "creative_preview", "route_trace_overlay", "performance_monitor"],
        "folders": ["themes", "expressions", "assets", "reports"],
        "status": "ok"
    }
    manifest_path = ROOT / "face_display" / "display_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main():
    print(f"Nova v1251_face_display_manifest")
    r = face_display_manifest()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
