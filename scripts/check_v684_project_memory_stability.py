#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v684_test_long_project_memory_stability import test_long_project_memory_stability
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v684_test_long_project_memory_stability -- Checker\n")
    c(Path(ROOT/"src"/"v684_test_long_project_memory_stability.py").exists(),"src exists")
    r=test_long_project_memory_stability(); c(r is not None,"result generated")
    recall=r.get("recall",{}) if r else {}
    c("v055_live" in recall,"v055_live present")
    c("v341_to_v450_passed" in recall,"v341_to_v450_passed present")
    c("v451_to_v650_built" in recall,"v451_to_v650_built present")
    c("robot_blocked" in recall,"robot_blocked present")
    c("planner_weakest" in recall,"planner_weakest present")
    c("proof_required" in recall,"proof_required present")
    c(recall.get("v055_live"),"v055_live is True")
    c(recall.get("v341_to_v450_passed"),"v341_to_v450_passed is True")
    c(recall.get("v451_to_v650_built"),"v451_to_v650_built is True")
    c(recall.get("robot_blocked"),"robot_blocked is True")
    c(recall.get("planner_weakest"),"planner_weakest is True")
    c(recall.get("proof_required"),"proof_required is True")
    c(r.get("all_recalled_correctly"),"all_recalled_correctly is True")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
