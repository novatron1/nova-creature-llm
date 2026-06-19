#!/usr/bin/env python3
"""Check v295_sim_to_hardware_gap_report."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v295_sim_to_hardware_gap_report import gap_report
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v295_sim_to_hardware_gap_report -- Checker\n")
    c(Path(ROOT/"src"/"v295_sim_to_hardware_gap_report.py").exists(),"src exists")
    r = gap_report()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
