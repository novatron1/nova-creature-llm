#!/usr/bin/env python3
"""Check v110_goal_memory."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v110_goal_memory import add_goal, list_goals
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v110_goal_memory -- Checker\n")
    c(Path(ROOT/"src"/"v110_goal_memory.py").exists(), "src exists")
    g = add_goal("Checker goal","test")
    c(g is not None, "goal added")
    c(len(list_goals()) > 0, "goals readable")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
