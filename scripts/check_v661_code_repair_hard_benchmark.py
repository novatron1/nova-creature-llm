#!/usr/bin/env python3
"""Check v661_planner_code_repair_hard_benchmark_3."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v661_planner_code_repair_hard_benchmark_3 import run_planner_code_repair_hard_benchmark_3
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v661_planner_code_repair_hard_benchmark_3 -- Checker\n")
    c(Path(ROOT/"src"/"v661_planner_code_repair_hard_benchmark_3.py").exists(),"src exists")
    r=run_planner_code_repair_hard_benchmark_3(); c(r is not None,"result generated")
    c(r.get("total_categories")==12,"12 test categories")
    cats=r.get("categories",{}); c(len(cats)==12,"12 category results")
    expected=["syntax_error_diagnosis","import_error","missing_file","broken_json",
               "assertion_repair","return_type","checkpoint_path","execution_order",
               "unsafe_rejection","patch_plan","test_rerun","rollback"]
    for cat in expected: c(cat in cats,f"category '{cat}' present")
    c("overall_score" in r,"overall_score present")
    c(r.get("passed","")+r.get("failed","")>=1,"some tests ran")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
