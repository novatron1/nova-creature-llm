#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v686_test_correct_brain_router import test_correct_brain_router
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v686_test_correct_brain_router -- Checker\n")
    c(Path(ROOT/"src"/"v686_test_correct_brain_router.py").exists(),"src exists")
    r=test_correct_brain_router(); c(r is not None,"result generated")
    routes=r.get("routes",{}) if r else {}
    c("code_repair" in routes,"code_repair route present")
    c("safety" in routes,"safety route present")
    c("history" in routes,"history route present")
    c("robot" in routes,"robot route present")
    c("business" in routes,"business route present")
    c("research" in routes,"research route present")
    c("app" in routes,"app route present")
    c(routes.get("code_repair")=="planner","code_repair->planner")
    c(routes.get("safety")=="critic","safety->critic")
    c(routes.get("history")=="memory","history->memory")
    c(routes.get("robot")=="safety","robot->safety")
    c(routes.get("business")=="business","business->business")
    c(routes.get("research")=="research","research->research")
    c(routes.get("app")=="app_builder","app->app_builder")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
