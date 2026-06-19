#!/usr/bin/env python3
"""Check v659_real_growth_evidence_folder."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v659_real_growth_evidence_folder import build_growth_evidence_folder
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v659_real_growth_evidence_folder -- Checker\n")
    c(Path(ROOT/"src"/"v659_real_growth_evidence_folder.py").exists(),"src exists")
    r=build_growth_evidence_folder(); c(r is not None,"result generated")
    c("evidence_path" in r,"evidence_path present")
    c("files_created" in r,"files_created present")
    c(r.get("total_files",0)==8,"8 evidence files created")
    ep=r.get("evidence_path",""); c("v659_real_growth" in ep,"path contains v659_real_growth")
    ep_path=Path(ep); c(ep_path.exists(),"evidence folder exists on disk")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
