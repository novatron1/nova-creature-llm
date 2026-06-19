#!/usr/bin/env python3
"""Check v087 multi-step planner."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v087_multistep_planner import plan_goal
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v087 -- Planner Checker\n")
    c(Path(ROOT/"src"/"v087_multistep_planner.py").exists(), "src exists")
    p = plan_goal("Make Nova smarter by improving reasoning, self-checking, and benchmarks.")
    c(len(p["steps"]) >= 5, f">=5 steps ({len(p['steps'])})")
    c("dependencies" in p, "dependencies listed")
    c("required_tests" in p, "tests required")
    c("safety_rules" in p, "safety rules present")
    c("next_action" in p, "next action defined")
    c("done_definition" in p, "done definition present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p_ in P: print(p_)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
