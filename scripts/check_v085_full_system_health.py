#!/usr/bin/env python3
"""Check v085 full system health."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v085_full_system_health import build_full_health
E,P=[], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v085 -- Health Checker\n")
    c((ROOT/"src"/"v085_full_system_health.py").exists(), "src exists")
    r = build_full_health()
    organs_active = sum(1 for o in r["brain_organs"].values() if o["active"])
    c(organs_active >= 7, f"7 brain organs ({organs_active})")
    c("memory_systems" in r, "memory systems")
    c(r["robot_status"]["real_hardware_enabled"] == False, "robot disabled")
    c(r["robot_status"]["physical_movement_blocked"] == True, "movement blocked")
    c(len(r["missing_capabilities"]) >= 3, "missing caps listed")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p_ in P: print(p_)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
