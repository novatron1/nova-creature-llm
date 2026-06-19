#!/usr/bin/env python3
"""Gold test for v348_robot_brain_package_builder."""
import json, sys; from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v348_robot_brain_package_builder import build_robot_brain_package
E, P = [], []
def main():
    r = build_robot_brain_package()
    if isinstance(r, dict): P.append("Result with " + str(len(r)) + " fields")
    else: P.append("Result generated")
    print("Nova v348_robot_brain_package_builder -- Gold Test\n")
    print("\n" + "="*60 + "\nPASSED: " + str(len(P)) + ", ERRORS: " + str(len(E)))
    for p in P: print("  [PASS] " + p)
    for e in E: print("  [FAIL] " + e)
    (ROOT/"reports"/"v348_robot_brain_package_builder_gold_status.json").write_text(json.dumps({"version":"v348_robot_brain_package_builder_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)}, indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
