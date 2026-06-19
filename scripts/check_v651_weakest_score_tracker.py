#!/usr/bin/env python3
"""Check v651_weakest_score_tracker."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v651_weakest_score_tracker import track_weakest_score
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v651_weakest_score_tracker -- Checker\n")
    c(Path(ROOT/"src"/"v651_weakest_score_tracker.py").exists(),"src exists")
    r=track_weakest_score(); c(r is not None,"result generated")
    c(r.get("weakest_role")=="planner_transformer","weakest role correct")
    c(r.get("weakest_skill")=="code_repair","weakest skill correct")
    c(r.get("score_before")==75,"score before 75")
    c(r.get("target_score")==85,"target 85")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
