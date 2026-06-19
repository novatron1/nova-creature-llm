#!/usr/bin/env python3
"""Check v405_research_priority_ranker."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v405_research_priority_ranker import rank_research_priority
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v405_research_priority_ranker -- Checker\n")
    c(Path(ROOT/"src"/"v405_research_priority_ranker.py").exists(),"src exists")
    r = rank_research_priority()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
