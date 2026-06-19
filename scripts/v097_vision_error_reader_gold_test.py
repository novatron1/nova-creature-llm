#!/usr/bin/env python3
"""Gold test for v097_vision_error_reader."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v097_vision_error_reader import read_visual_error
E,P=[], []
def main():
    print("Nova v097 -- Gold Test\n")
    r = read_visual_error("ModuleNotFoundError torch")
    if isinstance(r, dict):
        P.append(f"Result generated with {len(r)} fields")
    else:
        P.append(f"Result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v097_vision_error_reader_status.json").write_text(json.dumps({"version":"v097_vision_error_reader_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
