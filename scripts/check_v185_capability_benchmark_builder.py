#!/usr/bin/env python3
"""Check v185_capability_benchmark_builder."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v185_capability_benchmark_builder import build_capability_benchmark
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v185_capability_benchmark_builder -- Checker\n")
    c(Path(ROOT/"src"/"v185_capability_benchmark_builder.py").exists(), "src exists")
    r = build_capability_benchmark({"capability_name":"code_repair"})
    c(r is not None, "result generated")
    c(len(r["tests"]) >= 3, "tests built")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
