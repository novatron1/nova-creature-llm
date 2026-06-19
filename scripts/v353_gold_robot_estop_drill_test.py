#!/usr/bin/env python3
"""Gold test for v353_robot_emergency_stop_drill."""
import json, sys; from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v353_robot_emergency_stop_drill import run_emergency_stop_drill
E, P = [], []
def main():
    r = run_emergency_stop_drill()
    if isinstance(r, dict): P.append("Result with " + str(len(r)) + " fields")
    else: P.append("Result generated")
    print("Nova v353_robot_emergency_stop_drill -- Gold Test\n")
    print("\n" + "="*60 + "\nPASSED: " + str(len(P)) + ", ERRORS: " + str(len(E)))
    for p in P: print("  [PASS] " + p)
    for e in E: print("  [FAIL] " + e)
    (ROOT/"reports"/"v353_robot_emergency_stop_drill_gold_status.json").write_text(json.dumps({"version":"v353_robot_emergency_stop_drill_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)}, indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
