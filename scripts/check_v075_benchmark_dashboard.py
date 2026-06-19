#!/usr/bin/env python3
"""Check v075 benchmark dashboard."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v075_benchmark_dashboard import run_all_benchmarks, BENCHMARK_TESTS
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  \u2705 {msg}")
    else: E.append(f"  \u274c {msg}")
def main():
    print("Nova v075 -- Benchmark Dashboard Checker\n")
    c(Path(ROOT/"src"/"v075_benchmark_dashboard.py").exists(), "src exists")
    r = run_all_benchmarks()
    c(r["total_tests"] == 13, f"13 tests ({r['total_tests']})")
    c(r["all_passed"] or r["total_passed"] >= 10, f"most pass ({r['total_passed']}/{r['total_tests']})")
    c(r["overall_percentage"] > 0, f"percentage: {r['overall_percentage']}%")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
