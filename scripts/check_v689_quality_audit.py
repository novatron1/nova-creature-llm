#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v689_audit_intelligence_quality import audit_intelligence_quality
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v689_audit_intelligence_quality -- Checker\n")
    c(Path(ROOT/"src"/"v689_audit_intelligence_quality.py").exists(),"src exists")
    r=audit_intelligence_quality(); c(r is not None,"result generated")
    c("real_gain" in r,"real_gain present")
    c("fake_gain" in r,"fake_gain present")
    c("overclaim_risk" in r,"overclaim_risk present")
    c("regression_risk" in r,"regression_risk present")
    c("memory_pollution_risk" in r,"memory_pollution_risk present")
    c("promotion_readiness" in r,"promotion_readiness present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
