"""vv1287_display_run_guide — Nova Creature Face Display + Control Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def display_run_guide():
    """Module: Create guide: how to open display, use Face/Sensory/Creative/Private Mode, how to test display"""
    guide = {
        "how_to_open_display": "python face_display/run_display.py",
        "how_to_use_face_mode": "Nova's face shows expressions, eye movement, and mouth animation during speech",
        "how_to_use_sensory_mode": "Switch to sensory panel to see camera/mic/speaker/screen status and permissions",
        "how_to_use_creative_mode": "Switch to creative preview panel to see SVG/canvas/animation output",
        "how_to_use_private_mode": "Toggle private mode to stop all sensors and clear temporary session",
        "how_to_test_display": "python src/v1279_display_test_harness.py"
    }
    return {"version": "v1287_display_run_guide", "created_at": datetime.now().isoformat(),
            "module": "Create guide: how to open display, use Face/Sensory/Creative/Private Mode, how to test display", "guide": guide, "status": "ok"}


def main():
    print(f"Nova v1287_display_run_guide")
    r = display_run_guide()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
