#!/usr/bin/env python3
"""Check v254_important_fact_extractor."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v254_important_fact_extractor import extract_facts
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v254_important_fact_extractor -- Checker\n")
    c(Path(ROOT/"src"/"v254_important_fact_extractor.py").exists(),"src exists")
    r = extract_facts()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
