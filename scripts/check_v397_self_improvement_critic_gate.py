#!/usr/bin/env python3
"""Check v397_self_improvement_critic_gate."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v397_self_improvement_critic_gate import gate_self_improvement
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v397_self_improvement_critic_gate -- Checker\n")
    c(Path(ROOT/"src"/"v397_self_improvement_critic_gate.py").exists(),"src exists")
    r = gate_self_improvement()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
