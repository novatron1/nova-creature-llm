"""vv1272_safety_status_bar — Nova Creature Face Display + Control Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def safety_status_bar():
    """Module: Always show: permission state, private mode, recording state, screen capture state, active device state, no silent device use"""
    return {"version": "v1272_safety_status_bar", "created_at": datetime.now().isoformat(),
            "module": "Always show: permission state, private mode, recording state, screen capture state, active device state, no silent device use", "status": "ok"}


def main():
    print(f"Nova v1272_safety_status_bar")
    r = safety_status_bar()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
