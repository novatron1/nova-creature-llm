#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v698_real_intelligence_dashboard import generate_real_intelligence_dashboard
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v698_real_intelligence_dashboard -- Checker\n")
    c(Path(ROOT/"src"/"v698_real_intelligence_dashboard.py").exists(),"src exists")
    r=generate_real_intelligence_dashboard(); c(r is not None,"result generated")
    db=r.get("dashboard",{}); c("brain_maturity" in db,"brain maturity present")
    c("weakest_role" in db,"weakest role present")
    c("strongest_role" in db,"strongest role present")
    c("next_safe_upgrade" in db,"next safe upgrade present")
    c(len(db)>=9,"dashboard has 9+ fields")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
