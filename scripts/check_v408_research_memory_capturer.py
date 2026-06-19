#!/usr/bin/env python3
"""Check v408_research_memory_capturer."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v408_research_memory_capturer import capture_research_memory
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v408_research_memory_capturer -- Checker\n")
    c(Path(ROOT/"src"/"v408_research_memory_capturer.py").exists(),"src exists")
    r = capture_research_memory()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
