#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v700_real_intelligence_growth_final_report import generate_real_intelligence_growth_final_report
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v700_real_intelligence_growth_final_report -- Checker\n")
    c(Path(ROOT/"src"/"v700_real_intelligence_growth_final_report.py").exists(),"src exists")
    r=generate_real_intelligence_growth_final_report(); c(r is not None,"result generated")
    c(r.get("growth_proven"),"growth proven flag set")
    c("YES" in r.get("final_answer",""),"final answer confirms growth")
    es=r.get("evidence_summary",{}); c(es.get("total_modules",0)==700,"700 total modules")
    c("conclusion" in r,"conclusion present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
