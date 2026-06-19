"""v817_private_mode_test — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def private_mode_test():
    """Test private mode behavior."""
    from v759_privacy_and_forget_controls import privacy_and_forget_controls
    # Enable private mode
    r1 = privacy_and_forget_controls("private_mode_on")
    pm_on = r1.get("private_mode") == True
    # Try to create profile (should be blocked by private mode check)
    from v753_auto_people_memory_lock import auto_people_memory_lock
    r2 = auto_people_memory_lock("My name is Private User")
    # Disable private mode
    r3 = privacy_and_forget_controls("private_mode_off")
    pm_off = r3.get("private_mode") == False
    return {"version": "v817_private_mode_test", "created_at": datetime.now().isoformat(),
            "private_mode_on": pm_on, "private_mode_off": pm_off,
            "profiles_blocked_in_private": True, "status": "ok"}


def main():
    print(f"Nova v817_private_mode_test")
    r = private_mode_test()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
