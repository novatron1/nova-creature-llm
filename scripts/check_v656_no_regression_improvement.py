#!/usr/bin/env python3
"""Check v656_improvement_without_regression_checker."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v656_improvement_without_regression_checker import check_improvement_without_regression
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v656_improvement_without_regression_checker -- Checker\n")
    c(Path(ROOT/"src"/"v656_improvement_without_regression_checker.py").exists(),"src exists")
    r=check_improvement_without_regression(); c(r is not None,"result generated")
    checks=r.get("checks",{}); c(len(checks)==4,"4 checks performed")
    c("regression_check" in checks,"regression check present")
    c("robot_honesty_check" in checks,"robot honesty check present")
    c("memory_law_check" in checks,"memory law check present")
    c("fake_capability_claim" in checks,"fake capability claim check present")
    c("improvement_valid" in r,"improvement_valid status present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
