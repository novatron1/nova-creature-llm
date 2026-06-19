#!/usr/bin/env python3
"""Check v662_code_repair_score_tracker."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v662_code_repair_score_tracker import track_code_repair_score
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v662_code_repair_score_tracker -- Checker\n")
    c(Path(ROOT/"src"/"v662_code_repair_score_tracker.py").exists(),"src exists")
    r=track_code_repair_score(); c(r is not None,"result generated")
    c(r.get("current_score")==75,"current_score is 75")
    c(r.get("target")==85,"target is 85")
    c("exact_gaps" in r,"exact_gaps present")
    c("needed_lessons" in r,"needed_lessons present")
    c(r.get("target_met") is False,"target_met is False")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
