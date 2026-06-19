#!/usr/bin/env python3
"""Check v351_robot_skill_benchmark."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v351_robot_skill_benchmark import run_skill_benchmark
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v351_robot_skill_benchmark -- Checker\n")
    c(Path(ROOT/"src"/"v351_robot_skill_benchmark.py").exists(), "src exists")
    r = run_skill_benchmark()
    c(r is not None, "result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
