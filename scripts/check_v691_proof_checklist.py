#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v691_real_intelligence_proof import check_real_intelligence_proof
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v691_real_intelligence_proof -- Checker\n")
    c(Path(ROOT/"src"/"v691_real_intelligence_proof.py").exists(),"src exists")
    r=check_real_intelligence_proof(); c(r is not None,"result generated")
    c(r.get("all_checks_passed"),"all 14 proof checks passed")
    checks=r.get("checks",{}); c(len(checks)==14,"14 checks present")
    for k,v in checks.items(): c(v,f"check: {k}")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
