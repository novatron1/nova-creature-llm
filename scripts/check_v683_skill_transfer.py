#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v683_test_skill_transfer import test_skill_transfer
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v683_test_skill_transfer -- Checker\n")
    c(Path(ROOT/"src"/"v683_test_skill_transfer.py").exists(),"src exists")
    r=test_skill_transfer(); c(r is not None,"result generated")
    c("domain_pairs" in r,"domain_pairs present")
    dp=r.get("domain_pairs",{})
    c("code_repair_to_app_builder" in dp,"code_repair_to_app_builder present")
    c("evidence_to_research" in dp,"evidence_to_research present")
    c("continuity_to_business" in dp,"continuity_to_business present")
    c("robot_safety_to_computer_safety" in dp,"robot_safety_to_computer_safety present")
    c("identity_to_memory" in dp,"identity_to_memory present")
    c("average_transfer_quality" in r,"average_transfer_quality present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
