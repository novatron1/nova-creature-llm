#!/usr/bin/env python3
"""Check v663_drill_to_training_converter."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v663_drill_to_training_converter import convert_drills_to_training
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v663_drill_to_training_converter -- Checker\n")
    c(Path(ROOT/"src"/"v663_drill_to_training_converter.py").exists(),"src exists")
    c(Path(ROOT/"exports"/"v663_planner_training_candidates"/"planner_transformer_code_repair.jsonl").exists(),"training data exists")
    r=convert_drills_to_training(); c(r is not None,"result generated")
    c("drills_found" in r,"drills_found present")
    c("criteria_applied" in r,"criteria_applied present")
    c(r.get("status")=="converted","status is converted")
    c(r.get("drills_found",0)>=1,"at least 1 drill converted")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
