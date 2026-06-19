#!/usr/bin/env python3
"""Check v666_candidate_benchmark_runner."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v666_candidate_benchmark_runner import run_planner_candidate_benchmark
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v666_candidate_benchmark_runner -- Checker\n")
    c(Path(ROOT/"src"/"v666_candidate_benchmark_runner.py").exists(),"src exists")
    r=run_planner_candidate_benchmark(); c(r is not None,"result generated")
    c("results" in r,"results present")
    res=r.get("results",{}); c("v055_planner" in res,"v055_planner in results")
    c("v665_candidate" in res,"v665_candidate in results")
    c("baseline" in res,"baseline in results")
    c("improvements" in r,"improvements present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
