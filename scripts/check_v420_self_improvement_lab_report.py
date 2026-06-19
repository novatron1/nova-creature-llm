#!/usr/bin/env python3
"""Check v420_self_improvement_lab_report."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v420_self_improvement_lab_report import generate_self_improvement_lab_report
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v420_self_improvement_lab_report -- Checker\n")
    c(Path(ROOT/"src"/"v420_self_improvement_lab_report.py").exists(),"src exists")
    r = generate_self_improvement_lab_report()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
