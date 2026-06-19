#!/usr/bin/env python3
"""Check v384_multi_brain_drill_cooldown."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v384_multi_brain_drill_cooldown import track_drill_cooldown
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v384_multi_brain_drill_cooldown -- Checker\n")
    c(Path(ROOT/"src"/"v384_multi_brain_drill_cooldown.py").exists(),"src exists")
    r = track_drill_cooldown()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
