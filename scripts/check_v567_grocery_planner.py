#!/usr/bin/env python3
"""Check v567_grocery_planner."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v567_grocery_planner import plan_grocery
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v567_grocery_planner -- Checker\n")
    c(Path(ROOT/"src"/"v567_grocery_planner.py").exists(), "src exists")
    r = plan_grocery()
    c(r is not None, "result generated")
    c(isinstance(r, dict), "result is dict")
    c("version" in r, "version field present")
    c("created_at" in r, "created_at field present")
    c("simulation" in r, "simulation field present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
