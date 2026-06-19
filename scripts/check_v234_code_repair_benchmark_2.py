#!/usr/bin/env python3
"""Check v234_code_repair_benchmark_2."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v234_code_repair_benchmark_2 import run_benchmark
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v234_code_repair_benchmark_2 -- Checker\n")
    c(Path(ROOT/"src"/"v234_code_repair_benchmark_2.py").exists(), "src exists")
    r = run_benchmark()
    c(r is not None,"result generated")
    c(r["all_passed"],"all pass")
    c(r["total"]>=5,"8 tests")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
