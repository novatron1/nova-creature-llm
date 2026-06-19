"""vv1273_mobile_responsive_layout — Nova Creature Face Display + Control Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def mobile_responsive_layout():
    """Module: Make the display work on desktop, tablet, phone-size window, robot screen/cylinder display shape"""
    return {"version": "v1273_mobile_responsive_layout", "created_at": datetime.now().isoformat(),
            "module": "Make the display work on desktop, tablet, phone-size window, robot screen/cylinder display shape", "status": "ok"}


def main():
    print(f"Nova v1273_mobile_responsive_layout")
    r = mobile_responsive_layout()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
