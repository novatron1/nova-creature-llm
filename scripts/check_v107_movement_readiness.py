#!/usr/bin/env python3
"""Check v107_movement_readiness."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v107_movement_readiness import check_movement_readiness
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v107 -- Checker\n")
    c(Path(ROOT/"src"/"v107_movement_readiness.py").exists(), "src exists")
    r = check_movement_readiness()
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    c(not r['real_world_movement_allowed'], f"real movement blocked")
    c(len(r['missing_requirements']) >= 5, f"missing requirements listed")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
