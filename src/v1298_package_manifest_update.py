"""vv1298_package_manifest_update — Nova Creature Face Display + Control Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def package_manifest_update():
    """Module: Update package manifest to include v1251-v1300 display runtime"""
    update = {
        "version": "v1298_package_manifest_update",
        "created_at": datetime.now().isoformat(),
        "module": "Update package manifest to include v1251-v1300 display runtime",
        "updated_ranges": ["v1251-v1300"],
        "components_added": [
            "face_display", "expression_engine", "mouth_animation", "eye_engine",
            "brain_route_lights", "sensory_panel", "learning_memory_panel",
            "chat_panel", "creative_preview", "robot_screen",
            "permission_controls", "safety_bar", "display_benchmark",
        ],
        "status": "ok"
    }
    return update


def main():
    print(f"Nova v1298_package_manifest_update")
    r = package_manifest_update()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
