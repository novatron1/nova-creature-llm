#!/usr/bin/env python3
"""Check v382_role_brain_weakness_detector_3."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v382_role_brain_weakness_detector_3 import detect_role_weaknesses
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v382_role_brain_weakness_detector_3 -- Checker\n")
    c(Path(ROOT/"src"/"v382_role_brain_weakness_detector_3.py").exists(),"src exists")
    r = detect_role_weaknesses()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
