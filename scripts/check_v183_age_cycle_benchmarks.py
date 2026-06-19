#!/usr/bin/env python3
"""Check v183_age_cycle_benchmarks."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v183_age_cycle_benchmark_pack import run_age_cycle_benchmarks
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v183_age_cycle_benchmarks -- Checker\n")
    c(Path(ROOT/"src"/"v183_age_cycle_benchmark_pack.py").exists(), "src exists")
    r = run_age_cycle_benchmarks()
    c(r is not None, "result generated")
    c(r["total"] >= 8, f"{r['total']} benchmark categories")
    c(r["all_passed"], "all benchmarks pass")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
