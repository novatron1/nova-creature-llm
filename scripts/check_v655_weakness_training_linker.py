#!/usr/bin/env python3
"""Check v655_weakness_to_training_proof_linker."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v655_weakness_to_training_proof_linker import link_weakness_to_training_proof
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v655_weakness_to_training_proof_linker -- Checker\n")
    c(Path(ROOT/"src"/"v655_weakness_to_training_proof_linker.py").exists(),"src exists")
    r=link_weakness_to_training_proof(); c(r is not None,"result generated")
    chain=r.get("chain",{}); c(len(chain)==6,"6 links in chain")
    c("weakness" in chain,"weakness link present")
    c("lesson" in chain,"lesson link present")
    c("candidate" in chain,"candidate link present")
    c("benchmark" in chain,"benchmark link present")
    c("score" in chain,"score link present")
    c("tournament" in chain,"tournament link present")
    c(r.get("validated")==True,"chain validated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
