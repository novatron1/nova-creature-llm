#!/usr/bin/env python3
"""Check v108_mission_planner."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v108_mission_planner import plan_mission
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v108_mission_planner -- Checker\n")
    c(Path(ROOT/"src"/"v108_mission_planner.py").exists(), "src exists")
    r = plan_mission("Test mission")
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    c(len(r.get('phases',[])) >= 2, "phases defined")
    c(len(r.get('safety_rules',[])) >= 1, "safety rules present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
