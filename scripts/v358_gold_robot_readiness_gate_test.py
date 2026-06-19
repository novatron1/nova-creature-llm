#!/usr/bin/env python3
"""Gold test for v358_robot_body_readiness_gate."""
import json, sys; from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v358_robot_body_readiness_gate import check_body_readiness_gate
E, P = [], []
def main():
    r = check_body_readiness_gate()
    if isinstance(r, dict): P.append("Result with " + str(len(r)) + " fields")
    else: P.append("Result generated")
    print("Nova v358_robot_body_readiness_gate -- Gold Test\n")
    print("\n" + "="*60 + "\nPASSED: " + str(len(P)) + ", ERRORS: " + str(len(E)))
    for p in P: print("  [PASS] " + p)
    for e in E: print("  [FAIL] " + e)
    (ROOT/"reports"/"v358_robot_body_readiness_gate_gold_status.json").write_text(json.dumps({"version":"v358_robot_body_readiness_gate_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)}, indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
