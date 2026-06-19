#!/usr/bin/env python3
"""Check v364_drill_difficulty_escalator."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v364_drill_difficulty_escalator import escalate_difficulty
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v364_drill_difficulty_escalator -- Checker\n")
    c(Path(ROOT/"src"/"v364_drill_difficulty_escalator.py").exists(),"src exists")
    r = escalate_difficulty()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
