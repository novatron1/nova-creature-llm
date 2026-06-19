#!/usr/bin/env python3
"""Check v185_promotion_decision."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v185_age_cycle_promotion_decision import decide_promotion
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v185_promotion_decision -- Checker\n")
    c(Path(ROOT/"src"/"v185_age_cycle_promotion_decision.py").exists(), "src exists")
    r = decide_promotion()
    c(r is not None, "result generated")
    c("decision" in r, "decision made")
    c(r["robot_movement_still_blocked"], "robot movement blocked")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
