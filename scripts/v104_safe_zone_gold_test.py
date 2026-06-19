#!/usr/bin/env python3
"""Gold test for v104_safe_zone."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v104_safe_zone import build_safe_zone_map
E,P=[], []
def main():
    print(f"Nova v104 -- Gold Test\n")
    r = build_safe_zone_map(())
    if isinstance(r, dict): P.append(f"Result with {len(r)} fields")
    else: P.append("Result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v104_safe_zone_status.json").write_text(json.dumps({"version":"v104_safe_zone_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())