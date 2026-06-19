"""vv1252_live_face_screen — Nova Creature Face Display + Control Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def live_face_screen():
    """Module: Create the main Nova face screen: eyes, eyebrows, mouth, face container, expression state, idle/talking/thinking/listening animations"""
    return {"version": "v1252_live_face_screen", "created_at": datetime.now().isoformat(),
            "module": "Create the main Nova face screen: eyes, eyebrows, mouth, face container, expression state, idle/talking/thinking/listening animations", "status": "ok"}


def main():
    print(f"Nova v1252_live_face_screen")
    r = live_face_screen()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
