#!/usr/bin/env python3
"""Check v202_capability_to_benchmark_auto_builder."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v202_capability_to_benchmark_auto_builder import auto_build_benchmark
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v202_capability_to_benchmark_auto_builder -- Checker\n")
    c(Path(ROOT/"src"/"v202_capability_to_benchmark_auto_builder.py").exists(), "src exists")
    r = auto_build_benchmark("arithmetic")
    c(r is not None,"result generated")
    c(len(r["tests"])>=3,"tests built")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
