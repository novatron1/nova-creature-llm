#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v687_test_training_plan_self_improvement import test_training_plan_self_improvement
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v687_test_training_plan_self_improvement -- Checker\n")
    c(Path(ROOT/"src"/"v687_test_training_plan_self_improvement.py").exists(),"src exists")
    r=test_training_plan_self_improvement(); c(r is not None,"result generated")
    c("what_worked" in r,"what_worked present")
    c("what_failed" in r,"what_failed present")
    c("benchmark_too_easy" in r,"benchmark_too_easy present")
    c("role_needs_training" in r,"role_needs_training present")
    c("lessons_rejected" in r,"lessons_rejected present")
    c("promote_or_not" in r,"promote_or_not present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
