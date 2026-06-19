#!/usr/bin/env python3
"""Check v668_code_repair_regression_shield."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v668_code_repair_regression_shield import run_code_repair_regression_shield
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v668_code_repair_regression_shield -- Checker\n")
    c(Path(ROOT/"src"/"v668_code_repair_regression_shield.py").exists(),"src exists")
    r=run_code_repair_regression_shield(); c(r is not None,"result generated")
    c("traps" in r,"traps present")
    traps=r.get("traps",{}); c(len(traps)==6,"6 traps defined")
    expected=["unsafe_rm_delete","fake_success","hallucinated_path","wrong_checkpoint","dirty_data","robot_movement"]
    for t in expected: c(t in traps,f"trap '{t}' present")
    c("shield_active" in r,"shield_active present")
    c(r.get("shield_active") is True,"shield is active")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
