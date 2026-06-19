#!/usr/bin/env python3
"""Check v658_hard_vs_gold_separator."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v658_hard_vs_gold_separator import separate_hard_vs_gold
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v658_hard_vs_gold_separator -- Checker\n")
    c(Path(ROOT/"src"/"v658_hard_vs_gold_separator.py").exists(),"src exists")
    r=separate_hard_vs_gold(); c(r is not None,"result generated")
    cats=r.get("test_categories",{}); c(len(cats)==4,"4 test categories")
    c("gold_tests" in cats,"gold_tests category present")
    c("hard_tests" in cats,"hard_tests category present")
    c("adversarial_tests" in cats,"adversarial_tests category present")
    c("tournament_tests" in cats,"tournament_tests category present")
    c(cats["gold_tests"].get("purpose")=="installation","gold = installation")
    c(cats["hard_tests"].get("purpose")=="intelligence_gain","hard = intelligence_gain")
    c(cats["adversarial_tests"].get("purpose")=="robustness","adversarial = robustness")
    c(cats["tournament_tests"].get("purpose")=="promotion","tournament = promotion")
    c(r.get("separation_valid")==True,"separation valid")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
