#!/usr/bin/env python3
"""Check v355_robot_action_planner_simulator."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v355_robot_action_planner_simulator import run_action_planner_simulation
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v355_robot_action_planner_simulator -- Checker\n")
    c(Path(ROOT/"src"/"v355_robot_action_planner_simulator.py").exists(), "src exists")
    r = run_action_planner_simulation()
    c(r is not None, "result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
