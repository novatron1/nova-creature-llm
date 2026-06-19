#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v685_test_capability_boundary_honesty import test_capability_boundary_honesty
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v685_test_capability_boundary_honesty -- Checker\n")
    c(Path(ROOT/"src"/"v685_test_capability_boundary_honesty.py").exists(),"src exists")
    r=test_capability_boundary_honesty(); c(r is not None,"result generated")
    c("proven" in r,"proven present")
    c("unproven" in r,"unproven present")
    c("simulation_only" in r,"simulation_only present")
    c("blocked" in r,"blocked present")
    c("needs_owner_approval" in r,"needs_owner_approval present")
    c("unavailable_tool" in r,"unavailable_tool present")
    c(len(r.get("proven",[]))>=1,"at least 1 proven")
    c(len(r.get("unproven",[]))>=1,"at least 1 unproven")
    c(len(r.get("blocked",[]))>=1,"at least 1 blocked")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
