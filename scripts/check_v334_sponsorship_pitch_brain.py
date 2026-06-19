#!/usr/bin/env python3
"""Check v334_sponsorship_pitch_brain."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v334_sponsorship_pitch_brain import write_pitch
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v334_sponsorship_pitch_brain -- Checker\n")
    c(Path(ROOT/"src"/"v334_sponsorship_pitch_brain.py").exists(),"src exists")
    r = write_pitch()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
