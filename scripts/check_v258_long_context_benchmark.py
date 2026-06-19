#!/usr/bin/env python3
"""Check v258_long_context_benchmark."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v258_long_context_benchmark import run_benchmark
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v258_long_context_benchmark -- Checker\n")
    c(Path(ROOT/"src"/"v258_long_context_benchmark.py").exists(),"src exists")
    r = run_benchmark()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
