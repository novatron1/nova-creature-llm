#!/usr/bin/env python3
"""Check v223_goal_state_tracker."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v223_goal_state_tracker import track_goal
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v223_goal_state_tracker -- Checker\n")
    c(Path(ROOT/"src"/"v223_goal_state_tracker.py").exists(), "src exists")
    r = track_goal()
    c(r is not None,"result generated")
    c("goal" in r,"goal tracked")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
