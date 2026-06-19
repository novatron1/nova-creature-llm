#!/usr/bin/env python3
"""Check v140_model_evolution."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v140_model_evolution_report import generate_evolution_report
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v140_model_evolution -- Checker\n")
    c(Path(ROOT/"src"/"v140_model_evolution_report.py").exists(), "src exists")
    r = generate_evolution_report()
    c(r is not None, "result generated")
    c(r['total_versions'] >= 80, f"evolution tracked: {r['total_versions']} versions")
    c(not r['real_robot_movement_allowed'], "robot movement blocked")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
