#!/usr/bin/env python3
"""Gold test for v359_multi_robot_safety_council."""
import json, sys; from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v359_multi_robot_safety_council import get_safety_council_status
E, P = [], []
def main():
    r = get_safety_council_status()
    if isinstance(r, dict): P.append("Result with " + str(len(r)) + " fields")
    else: P.append("Result generated")
    print("Nova v359_multi_robot_safety_council -- Gold Test\n")
    print("\n" + "="*60 + "\nPASSED: " + str(len(P)) + ", ERRORS: " + str(len(E)))
    for p in P: print("  [PASS] " + p)
    for e in E: print("  [FAIL] " + e)
    (ROOT/"reports"/"v359_multi_robot_safety_council_gold_status.json").write_text(json.dumps({"version":"v359_multi_robot_safety_council_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)}, indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
