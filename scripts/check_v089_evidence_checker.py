#!/usr/bin/env python3
"""Check check_v089_evidence_checker."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v089_evidence_checker import check_evidence
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v089 -- Checker\n")
    c(True, "src module exists")
    check_evidence("Nova can move a real robot.")
    r = check_evidence("Nova can move a real robot.")
    if isinstance(r, tuple):
        r = r[0]

    c(r['is_speculation'] or not r['supported'], f"robot claim unsupported")

    c(isinstance(r['evidence_type'], str), f"evidence type present")

    c('should_answer' in r, f"should_answer present")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
