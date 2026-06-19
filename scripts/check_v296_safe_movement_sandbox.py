#!/usr/bin/env python3
"""Check v296_safe_movement_sandbox."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v296_safe_movement_sandbox import simulate
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v296_safe_movement_sandbox -- Checker\n")
    c(Path(ROOT/"src"/"v296_safe_movement_sandbox.py").exists(),"src exists")
    r = simulate()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
