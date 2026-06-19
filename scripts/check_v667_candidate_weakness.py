#!/usr/bin/env python3
"""Check v667_candidate_weakness_report."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v667_candidate_weakness_report import generate_candidate_weakness_report
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v667_candidate_weakness_report -- Checker\n")
    c(Path(ROOT/"src"/"v667_candidate_weakness_report.py").exists(),"src exists")
    r=generate_candidate_weakness_report(); c(r is not None,"result generated")
    c("improved" in r,"improved present")
    c("failed" in r,"failed present")
    c("stayed_same" in r,"stayed_same present")
    c("needs_more_training" in r,"needs_more_training present")
    c("target_85_reached" in r,"target_85_reached present")
    c(r.get("target_85_reached") is False,"target 85 not yet reached")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
