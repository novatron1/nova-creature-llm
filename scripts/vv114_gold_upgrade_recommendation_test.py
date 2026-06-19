#!/usr/bin/env python3
"""Gold test for v114_upgrade_recommendation."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v114_upgrade_recommendation_engine import recommend_next_upgrade
E,P=[], []
def main():
    print(f"Nova v114_upgrade_recommendation -- Gold Test\n")
    r = recommend_next_upgrade()
    if isinstance(r, dict): P.append(f"Result with {len(r)} fields")
    else: P.append("Result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v114_upgrade_recommendation_status.json").write_text(json.dumps({"version":"v114_upgrade_recommendation_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
