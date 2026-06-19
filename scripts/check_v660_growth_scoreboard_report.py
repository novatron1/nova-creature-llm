#!/usr/bin/env python3
"""Check v660_growth_scoreboard_report."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v660_growth_scoreboard_report import generate_growth_scoreboard_report
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v660_growth_scoreboard_report -- Checker\n")
    c(Path(ROOT/"src"/"v660_growth_scoreboard_report.py").exists(),"src exists")
    r=generate_growth_scoreboard_report(); c(r is not None,"result generated")
    c("report_title" in r,"report_title present")
    summary=r.get("summary",{}); c("total_modules" in summary,"total_modules in summary")
    c(summary.get("total_modules")==10,"10 total modules")
    c("module_status" in r,"module_status present")
    ms=r.get("module_status",{}); c(len(ms)==10,"10 module status entries")
    c("v651" in ms and "v660" in ms,"v651 through v660 covered")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
