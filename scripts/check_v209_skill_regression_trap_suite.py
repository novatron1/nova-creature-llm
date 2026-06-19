#!/usr/bin/env python3
"""Check v209_skill_regression_trap_suite."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v209_skill_regression_trap_suite import run_regression_traps
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v209_skill_regression_trap_suite -- Checker\n")
    c(Path(ROOT/"src"/"v209_skill_regression_trap_suite.py").exists(), "src exists")
    r = run_regression_traps()
    c(r is not None,"result generated")
    c(r["no_regressions"],"no regressions")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
