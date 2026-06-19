#!/usr/bin/env python3
"""v089 — Gold evidence test."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v089_evidence_checker import check_evidence
E, P = [], []
def main():
    print("Nova v089 -- Gold Evidence Test\n")
    r1 = check_evidence("Nova can move a real robot.")
    r2 = check_evidence("Nova has v059 live router promotion.")
    r3 = check_evidence("Maybe this checkpoint is best.")
    if r1["is_speculation"] or not r1["supported"]: P.append("Robot claim unsupported")
    else: E.append("Robot claim should be unsupported")
    if r2["evidence_type"] in ("direct_dictionary", "project_report", "inferred_from_context"): P.append("v059 claim processed")
    else: E.append(f"v059 claim type unexpected: {r2['evidence_type']}")
    if r3["is_speculation"] or not r3["supported"]: P.append("Speculation flagged")
    else: E.append("Speculation should be flagged")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v089_gold_evidence_test.json").write_text(json.dumps({"version":"v089_gold","passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
