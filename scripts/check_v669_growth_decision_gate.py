#!/usr/bin/env python3
"""Check v669_growth_decision_gate."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v669_growth_decision_gate import gate_planner_growth_decision
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v669_growth_decision_gate -- Checker\n")
    c(Path(ROOT/"src"/"v669_growth_decision_gate.py").exists(),"src exists")
    r=gate_planner_growth_decision(); c(r is not None,"result generated")
    c("status" in r,"status present")
    c(r.get("status") is not None,"status is set")
    c("gate_passed" in r,"gate_passed present")
    c("current_score" in r,"current_score present")
    c("improvement" in r,"improvement present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
