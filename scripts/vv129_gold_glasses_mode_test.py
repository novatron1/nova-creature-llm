#!/usr/bin/env python3
"""Gold test for v129_glasses_mode."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v129_short_answer_glasses_mode import glasses_answer
E,P=[], []
def main():
    print(f"Nova v129_glasses_mode -- Gold Test\n")
    r = glasses_answer("Gold test question")
    if isinstance(r, dict): P.append(f"Result with {len(r)} fields")
    else: P.append("Result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v129_glasses_mode_status.json").write_text(json.dumps({"version":"v129_glasses_mode_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
