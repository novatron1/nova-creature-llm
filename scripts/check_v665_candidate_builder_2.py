#!/usr/bin/env python3
"""Check v665_candidate_checkpoint_builder_2."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v665_candidate_checkpoint_builder_2 import build_planner_candidate_checkpoint_2
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v665_candidate_checkpoint_builder_2 -- Checker\n")
    c(Path(ROOT/"src"/"v665_candidate_checkpoint_builder_2.py").exists(),"src exists")
    r=build_planner_candidate_checkpoint_2(); c(r is not None,"result generated")
    c("candidate_status" in r,"candidate_status present")
    c(r.get("manifest_created") is True,"manifest was created")
    c("torch_available" in r,"torch_available present")
    c(Path(ROOT/"checkpoints"/"candidates"/"v665_planner_code_repair"/"planner_transformer_v665_manifest.json").exists(),"manifest file exists")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
