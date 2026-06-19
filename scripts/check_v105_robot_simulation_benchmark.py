#!/usr/bin/env python3
"""Check v105_robot_simulation_benchmark."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v105_robot_simulation_benchmark import run_robot_sim_benchmark
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v105 -- Checker\n")
    c(Path(ROOT/"src"/"v105_robot_simulation_benchmark.py").exists(), "src exists")
    r = run_robot_sim_benchmark()
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    c(r['all_passed'], f"all benchmarks pass")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
