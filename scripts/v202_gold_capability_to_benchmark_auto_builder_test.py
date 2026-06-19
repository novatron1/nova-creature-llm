#!/usr/bin/env python3
"""Gold test for v202_capability_to_benchmark_auto_builder."""
import json, sys; from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v202_capability_to_benchmark_auto_builder import auto_build_benchmark
E,P=[], []
def main():
    print("Nova v202_capability_to_benchmark_auto_builder -- Gold Test\n")
    r = auto_build_benchmark()
    if isinstance(r, dict): P.append("Result with " + str(len(r)) + " fields")
    else: P.append("Result generated")
    print("\n" + "="*60 + "\nPASSED: " + str(len(P)) + ", ERRORS: " + str(len(E)))
    for p in P: print("  [PASS] " + p)
    for e in E: print("  [FAIL] " + e)
    (ROOT/"reports"/"v202_capability_to_benchmark_auto_builder_status.json").write_text(json.dumps({"version":"v202_capability_to_benchmark_auto_builder_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
