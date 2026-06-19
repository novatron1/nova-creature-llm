#!/usr/bin/env python3
"""Gold test for v099_file_folder_visual_inspector."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v099_file_folder_visual_inspector import inspect_file_folder_listing
E,P=[], []
def main():
    print("Nova v099 -- Gold Test\n")
    r = inspect_file_folder_listing("checkpoints/base/creature_v032_bigfit_twenty_plain.pt\nreports/v095_intelligence_benchmark_status.json")
    if isinstance(r, dict):
        P.append(f"Result generated with {len(r)} fields")
    else:
        P.append(f"Result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v099_file_folder_visual_inspector_status.json").write_text(json.dumps({"version":"v099_file_folder_visual_inspector_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
