#!/usr/bin/env python3
"""Check v134_weakness_detector."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v134_weakness_detector import detect_weaknesses
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v134_weakness_detector -- Checker\n")
    c(Path(ROOT/"src"/"v134_weakness_detector.py").exists(), "src exists")
    r = detect_weaknesses()
    c(r is not None, "result generated")
    c(len(r.get('weaknesses',[])) >= 1, "weaknesses identified")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
