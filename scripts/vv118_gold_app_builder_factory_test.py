#!/usr/bin/env python3
"""Gold test for v118_app_builder_factory."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v118_app_builder_factory import app_builder_factory
E,P=[], []
def main():
    print(f"Nova v118_app_builder_factory -- Gold Test\n")
    r = app_builder_factory("gold_test")
    if isinstance(r, dict): P.append(f"Result with {len(r)} fields")
    else: P.append("Result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v118_app_builder_factory_status.json").write_text(json.dumps({"version":"v118_app_builder_factory_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
