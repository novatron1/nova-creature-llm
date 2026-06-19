#!/usr/bin/env python3
"""Check v654_intelligence_gain_meter_2."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v654_intelligence_gain_meter_2 import calculate_intelligence_gain_2
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v654_intelligence_gain_meter_2 -- Checker\n")
    c(Path(ROOT/"src"/"v654_intelligence_gain_meter_2.py").exists(),"src exists")
    r=calculate_intelligence_gain_2(); c(r is not None,"result generated")
    c("raw_gain" in r,"raw_gain present")
    c("safe_gain" in r,"safe_gain present")
    c("regression_penalty" in r,"regression_penalty present")
    c("overclaim_penalty" in r,"overclaim_penalty present")
    c("dirty_data_penalty" in r,"dirty_data_penalty present")
    c("final_gain_score" in r,"final_gain_score present")
    c(r.get("raw_gain",0)>=r.get("final_gain_score",0),"final gain <= raw gain")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
