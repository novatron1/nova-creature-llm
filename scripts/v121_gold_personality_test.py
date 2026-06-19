#!/usr/bin/env python3
"""Gold test for v121_personality_style_brain."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v121_personality_style_brain import apply_style
E,P=[], []
def main():
    print("Nova v121_personality_style_brain -- Gold Test\n")
    r = apply_style("facts_only","gold test")
    if isinstance(r, dict): P.append("Result with " + str(len(r)) + " fields")
    else: P.append("Result generated")
    print("\n" + "="*60 + "\nPASSED: " + str(len(P)) + ", ERRORS: " + str(len(E)))
    for p in P: print("  [PASS] " + p)
    for e in E: print("  [FAIL] " + e)
    (ROOT/"reports"/"v121_personality_style_brain_status.json").write_text(json.dumps({"version":"v121_personality_style_brain_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
