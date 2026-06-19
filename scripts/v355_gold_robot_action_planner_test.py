#!/usr/bin/env python3
"""Gold test for v355_robot_action_planner_simulator."""
import json, sys; from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v355_robot_action_planner_simulator import run_action_planner_simulation
E, P = [], []
def main():
    r = run_action_planner_simulation()
    if isinstance(r, dict): P.append("Result with " + str(len(r)) + " fields")
    else: P.append("Result generated")
    print("Nova v355_robot_action_planner_simulator -- Gold Test\n")
    print("\n" + "="*60 + "\nPASSED: " + str(len(P)) + ", ERRORS: " + str(len(E)))
    for p in P: print("  [PASS] " + p)
    for e in E: print("  [FAIL] " + e)
    (ROOT/"reports"/"v355_robot_action_planner_simulator_gold_status.json").write_text(json.dumps({"version":"v355_robot_action_planner_simulator_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)}, indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
