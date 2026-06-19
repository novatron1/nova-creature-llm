#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v697_live_router_promotion_guard import guard_live_router_promotion
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v697_live_router_promotion_guard -- Checker\n")
    c(Path(ROOT/"src"/"v697_live_router_promotion_guard.py").exists(),"src exists")
    r=guard_live_router_promotion(); c(r is not None,"result generated")
    c(r.get("dry_run_only"),"dry run mode enabled by default")
    guards=r.get("guard_checks",{}); c(len(guards)==5,"5 guard checks present")
    c("promotion_allowed" in r,"promotion status present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
