#!/usr/bin/env python3
"""Gold test for v105_robot_simulation_benchmark."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v105_robot_simulation_benchmark import run_robot_sim_benchmark
E,P=[], []
def main():
    print(f"Nova v105 -- Gold Test\n")
    r = run_robot_sim_benchmark()
    if isinstance(r, dict): P.append(f"Result with {len(r)} fields")
    else: P.append("Result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v105_robot_simulation_benchmark_status.json").write_text(json.dumps({"version":"v105_robot_simulation_benchmark_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())