#!/usr/bin/env python3
"""Check v670_growth_proof_report."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v670_growth_proof_report import generate_planner_growth_proof_report
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v670_growth_proof_report -- Checker\n")
    c(Path(ROOT/"src"/"v670_growth_proof_report.py").exists(),"src exists")
    r=generate_planner_growth_proof_report(); c(r is not None,"result generated")
    c("report_title" in r,"report_title present")
    summary=r.get("summary",{}); c("total_modules" in summary,"total_modules in summary")
    c(summary.get("total_modules")==10,"10 total modules")
    c("module_status" in r,"module_status present")
    ms=r.get("module_status",{}); c(len(ms)==10,"10 module status entries")
    c("v661" in ms and "v670" in ms,"v661 through v670 covered")
    c("target_85_analysis" in r,"target_85_analysis present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
