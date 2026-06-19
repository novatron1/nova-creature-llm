#!/usr/bin/env python3
"""Check v103_sensor_feedback."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v103_sensor_feedback import read_sensor_feedback
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v103 -- Checker\n")
    c(Path(ROOT/"src"/"v103_sensor_feedback.py").exists(), "src exists")
    r = read_sensor_feedback()
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    c(r['simulation_only'], f"simulation only")
    c(not r['real_hardware_enabled'], f"hardware disabled")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
