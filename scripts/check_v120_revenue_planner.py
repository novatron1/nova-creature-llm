#!/usr/bin/env python3
"""Check v120_revenue_planner."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v120_project_revenue_planner import revenue_planner_assist
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v120_revenue_planner -- Checker\n")
    c(Path(ROOT/"src"/"v120_project_revenue_planner.py").exists(), "src exists")
    r = revenue_planner_assist("test")
    c(r is not None, "result generated")
    c(len(r.get('capabilities',[])) >= 3, "capabilities defined")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
