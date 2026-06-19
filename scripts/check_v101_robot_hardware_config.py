#!/usr/bin/env python3
"""Check v101_robot_hardware_config."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v101_robot_hardware_config import read_robot_hardware_config
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v101 -- Checker\n")
    c(Path(ROOT/"src"/"v101_robot_hardware_config.py").exists(), "src exists")
    r = read_robot_hardware_config(())
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    c(not r.get('real_hardware_enabled', True), f"real hardware disabled")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
