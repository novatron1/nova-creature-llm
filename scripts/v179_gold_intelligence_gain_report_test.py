#!/usr/bin/env python3
"""Gold test for v179_intelligence_gain_report."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v179_intelligence_gain_report import generate_gain_report
E,P=[], []
def main():
    print("Nova v179_intelligence_gain_report -- Gold Test\n")
    r = generate_gain_report()
    if isinstance(r, dict): P.append("Result with " + str(len(r)) + " fields")
    else: P.append("Result generated")
    print("\n" + "="*60 + "\nPASSED: " + str(len(P)) + ", ERRORS: " + str(len(E)))
    for p in P: print("  [PASS] " + p)
    for e in E: print("  [FAIL] " + e)
    (ROOT/"reports"/"v179_intelligence_gain_report_status.json").write_text(json.dumps({"version":"v179_intelligence_gain_report_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
