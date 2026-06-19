#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v693_proven_growth_certificate import certify_proven_growth
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v693_proven_growth_certificate -- Checker\n")
    c(Path(ROOT/"src"/"v693_proven_growth_certificate.py").exists(),"src exists")
    r=certify_proven_growth(); c(r is not None,"result generated")
    c(r.get("status")=="proven_growth","status is proven_growth")
    c("available_statuses" in r,"available statuses present")
    c(len(r.get("available_statuses",[]))==6,"6 available statuses")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
