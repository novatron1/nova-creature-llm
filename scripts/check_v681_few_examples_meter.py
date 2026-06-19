#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v681_measure_few_examples_learning import measure_few_examples_learning
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v681_measure_few_examples_learning -- Checker\n")
    c(Path(ROOT/"src"/"v681_measure_few_examples_learning.py").exists(),"src exists")
    r=measure_few_examples_learning(); c(r is not None,"result generated")
    c("examples_used" in r,"examples_used present")
    c("score_gain" in r,"score_gain present")
    c("gain_per_example" in r,"gain_per_example present")
    c("role" in r,"role present")
    c("skill" in r,"skill present")
    c("efficiency_grade" in r,"efficiency_grade present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
