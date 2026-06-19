#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v699_system_integrity_final_regression import run_system_integrity_final_regression
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v699_system_integrity_final_regression -- Checker\n")
    c(Path(ROOT/"src"/"v699_system_integrity_final_regression.py").exists(),"src exists")
    r=run_system_integrity_final_regression(); c(r is not None,"result generated")
    rr=r.get("regression_results",{}); c(rr.get("all_passed"),"all regressions passed")
    c(rr.get("total_checks",0)==45,"45 total checks")
    c(rr.get("failed_checks",-1)==0,"0 failed checks")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
