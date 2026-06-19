#!/usr/bin/env python3
"""Check v238_planner_promotion_decision."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v238_planner_promotion_decision import decide
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v238_planner_promotion_decision -- Checker\n")
    c(Path(ROOT/"src"/"v238_planner_promotion_decision.py").exists(), "src exists")
    r = decide()
    c(r is not None,"result generated")
    c(r["decision"]=="preserve_v055","preserves v055")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
