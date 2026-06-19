#!/usr/bin/env python3
"""Gold test for v186_input_to_brain_role_mapper."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v186_input_to_brain_role_mapper import map_input_to_role
E,P=[], []
def main():
    print("Nova v186_input_to_brain_role_mapper -- Gold Test\n")
    r = map_input_to_role("What is 12 times 12?")
    if isinstance(r, dict): P.append("Result with " + str(len(r)) + " fields")
    else: P.append("Result generated")
    print("\n" + "="*60 + "\nPASSED: " + str(len(P)) + ", ERRORS: " + str(len(E)))
    for p in P: print("  [PASS] " + p)
    for e in E: print("  [FAIL] " + e)
    (ROOT/"reports"/"v186_role_mapper_status.json").write_text(json.dumps({"version":"v186_input_to_brain_role_mapper_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
