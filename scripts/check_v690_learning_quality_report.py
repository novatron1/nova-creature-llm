#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v690_generate_learning_quality_proof_report import generate_learning_quality_proof_report
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v690_generate_learning_quality_proof_report -- Checker\n")
    c(Path(ROOT/"src"/"v690_generate_learning_quality_proof_report.py").exists(),"src exists")
    r=generate_learning_quality_proof_report(); c(r is not None,"result generated")
    c("report_id" in r,"report_id present")
    c("modules" in r,"modules present")
    c(r.get("module_count")==10,"module_count is 10")
    c("focus_areas" in r,"focus_areas present")
    c("v681" in r.get("focus_areas",{}),"v681 in focus_areas")
    c("v690" in r.get("focus_areas",{}),"v690 in focus_areas")
    c("overall_status" in r,"overall_status present")
    c("promotion_readiness" in r,"promotion_readiness present")
    c(Path(ROOT/"reports"/"v681_to_v690_learning_quality_proof_status.json").exists(),"report file exists")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
