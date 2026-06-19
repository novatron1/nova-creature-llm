#!/usr/bin/env python3
"""Check v653_before_after_benchmark_comparator."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v653_before_after_benchmark_comparator import compare_before_after_benchmarks
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v653_before_after_benchmark_comparator -- Checker\n")
    c(Path(ROOT/"src"/"v653_before_after_benchmark_comparator.py").exists(),"src exists")
    r=compare_before_after_benchmarks(); c(r is not None,"result generated")
    c("v055_score" in r,"v055_score present")
    c("current_score" in r,"current_score present")
    c("candidate_score" in r,"candidate_score present")
    c("improvement_v055_to_current" in r,"improvement v055->current present")
    c("improvement_current_to_candidate" in r,"improvement current->candidate present")
    c("total_improvement_v055_to_candidate" in r,"total improvement present")
    c(r.get("consistent_improvement")==True,"consistent improvement confirmed")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
