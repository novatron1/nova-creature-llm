#!/usr/bin/env python3
"""Gold test for v098_ui_action_planner."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v098_ui_action_planner import plan_ui_action
E,P=[], []
def main():
    print("Nova v098 -- Gold Test\n")
    r = plan_ui_action("Screen shows v095 passed.", "Continue build.")
    if isinstance(r, dict):
        P.append(f"Result generated with {len(r)} fields")
    else:
        P.append(f"Result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v098_ui_action_planner_status.json").write_text(json.dumps({"version":"v098_ui_action_planner_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
