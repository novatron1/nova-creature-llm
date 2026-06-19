#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v695_next_checkpoint_tournament_planner import plan_next_checkpoint_tournament
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v695_next_checkpoint_tournament_planner -- Checker\n")
    c(Path(ROOT/"src"/"v695_next_checkpoint_tournament_planner.py").exists(),"src exists")
    r=plan_next_checkpoint_tournament(); c(r is not None,"result generated")
    tp=r.get("tournament_plan",{}); c("checkpoint_id" in tp,"checkpoint id present")
    c("benchmarks" in tp,"benchmarks present")
    c(r.get("estimated_duration_hours") is not None,"estimated duration present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
