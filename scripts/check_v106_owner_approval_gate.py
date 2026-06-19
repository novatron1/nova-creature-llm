#!/usr/bin/env python3
"""Check v106_owner_approval_gate."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v106_owner_approval_gate import check_owner_approval
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v106 -- Checker\n")
    c(Path(ROOT/"src"/"v106_owner_approval_gate.py").exists(), "src exists")
    r = check_owner_approval(("robot_physical_movement"))
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    c(r['requires_approval'], f"robot movement requires approval")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
