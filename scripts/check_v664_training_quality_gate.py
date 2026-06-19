#!/usr/bin/env python3
"""Check v664_training_quality_gate."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v664_training_quality_gate import gate_planner_training_quality
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v664_training_quality_gate -- Checker\n")
    c(Path(ROOT/"src"/"v664_training_quality_gate.py").exists(),"src exists")
    r=gate_planner_training_quality(); c(r is not None,"result generated")
    c("gate_results" in r,"gate_results present")
    c("all_gates_passed" in r,"all_gates_passed present")
    gates=r.get("gate_results",{}); c(len(gates)==7,"7 gates defined")
    c("blocked" in r,"blocked field present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
