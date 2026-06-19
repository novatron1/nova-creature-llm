#!/usr/bin/env python3
"""Check v225_learning_efficiency_optimizer."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v225_learning_efficiency_optimizer import optimize_efficiency
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v225_learning_efficiency_optimizer -- Checker\n")
    c(Path(ROOT/"src"/"v225_learning_efficiency_optimizer.py").exists(), "src exists")
    r = optimize_efficiency()
    c(r is not None,"result generated")
    c(len(r["optimizations"])>=3,"optimizations listed")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
