#!/usr/bin/env python3
"""Check v251_long_term_memory_compressor."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v251_long_term_memory_compressor import compress_memory
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v251_long_term_memory_compressor -- Checker\n")
    c(Path(ROOT/"src"/"v251_long_term_memory_compressor.py").exists(),"src exists")
    r = compress_memory()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
