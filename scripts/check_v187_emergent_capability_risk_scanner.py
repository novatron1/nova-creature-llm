#!/usr/bin/env python3
"""Check v187_emergent_capability_risk_scanner."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v187_emergent_capability_risk_scanner import scan_capability_risks, get_blocked
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v187_emergent_capability_risk_scanner -- Checker\n")
    c(Path(ROOT/"src"/"v187_emergent_capability_risk_scanner.py").exists(), "src exists")
    r = scan_capability_risks()
    c(r is not None, "result generated")
    c(r["total"] >= 1, "risks scanned")
    bl = get_blocked()
    c("real_robot_movement" in bl, "robot movement blocked")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
