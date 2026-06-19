#!/usr/bin/env python3
"""Check v155_hard_problem_gym."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v155_hard_problem_gym import generate_hard_problems
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v155_hard_problem_gym -- Checker\n")
    c(Path(ROOT/"src"/"v155_hard_problem_gym.py").exists(), "src exists")
    r = generate_hard_problems()
    c(r is not None, "result generated")
    c(len(r["problems"]) >= 7, f"{len(r["problems"])} problems")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
