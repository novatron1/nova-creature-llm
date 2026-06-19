#!/usr/bin/env python3
"""Check v191_unproven_capability_proof_benchmarks."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v191_unproven_capability_proof_benchmarks import run_unproven_proofs
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v191_unproven_capability_proof_benchmarks -- Checker\n")
    c(Path(ROOT/"src"/"v191_unproven_capability_proof_benchmarks.py").exists(), "src exists")
    r = run_unproven_proofs()
    c(r is not None,"result generated")
    c(r["all_passed"],"all proven")
    c(len(r["newly_proven"])>=2,"newly proven")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
