#!/usr/bin/env python3
"""Check v239_live_router_planner_update."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v239_live_router_planner_update import check_router_update
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v239_live_router_planner_update -- Checker\n")
    c(Path(ROOT/"src"/"v239_live_router_planner_update.py").exists(), "src exists")
    r = check_router_update(False)
    c(r is not None,"result generated")
    c(r["v055_preserved"],"v055 preserved")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
