#!/usr/bin/env python3
"""Check v283_app_scaffold_generator_2."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v283_app_scaffold_generator_2 import generate
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v283_app_scaffold_generator_2 -- Checker\n")
    c(Path(ROOT/"src"/"v283_app_scaffold_generator_2.py").exists(),"src exists")
    r = generate()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
