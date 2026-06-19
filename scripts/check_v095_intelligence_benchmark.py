#!/usr/bin/env python3
"""Check check_v095_intelligence_benchmark."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v095_intelligence_benchmark_suite import run_critical_tests
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v095 -- Checker\n")
    c(True, "src module exists")
    run_critical_tests()
    r = run_critical_tests()
    if isinstance(r, tuple):
        r = r[0]

    c(r['total_tests'] >= 5, f">=5 tests")

    c('all_critical_pass' in r, f"critical pass status")

    c('promote_ready' in r, f"promote readiness")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
