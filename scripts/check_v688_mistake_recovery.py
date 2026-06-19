#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v688_test_mistake_recovery_speed import test_mistake_recovery_speed
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v688_test_mistake_recovery_speed -- Checker\n")
    c(Path(ROOT/"src"/"v688_test_mistake_recovery_speed.py").exists(),"src exists")
    r=test_mistake_recovery_speed(); c(r is not None,"result generated")
    c("detect_time_ms" in r,"detect_time_ms present")
    c("classify_time_ms" in r,"classify_time_ms present")
    c("repair_plan_quality" in r,"repair_plan_quality present")
    c("lesson_created" in r,"lesson_created present")
    c("repeat_prevention" in r,"repeat_prevention present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
