#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v692_fake_intelligence_growth_detector import detect_fake_intelligence_growth
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v692_fake_intelligence_growth_detector -- Checker\n")
    c(Path(ROOT/"src"/"v692_fake_intelligence_growth_detector.py").exists(),"src exists")
    r=detect_fake_intelligence_growth(); c(r is not None,"result generated")
    det=r.get("detectors",{}); c(len(det)==7,"7 detectors present")
    c(r.get("fake_growth_detected")==False,"no fake growth detected")
    c(r.get("all_detectors_negative"),"all detectors negative")
    for k,v in det.items(): c(not v,f"detector {k} negative")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
