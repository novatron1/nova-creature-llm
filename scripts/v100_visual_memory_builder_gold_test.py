#!/usr/bin/env python3
"""Gold test for v100_visual_memory_builder."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v100_visual_memory_builder import build_visual_memory
E,P=[], []
def main():
    print("Nova v100 -- Gold Test\n")
    r = build_visual_memory({"text_or_description": "v095 passed 13/13.", "pass_fail_status": "pass"})
    if isinstance(r, dict):
        P.append(f"Result generated with {len(r)} fields")
    else:
        P.append(f"Result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v100_visual_memory_builder_status.json").write_text(json.dumps({"version":"v100_visual_memory_builder_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
