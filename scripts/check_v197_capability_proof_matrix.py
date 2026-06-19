#!/usr/bin/env python3
"""Check v197_capability_proof_matrix."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v197_capability_proof_matrix import build_proof_matrix
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v197_capability_proof_matrix -- Checker\n")
    c(Path(ROOT/"src"/"v197_capability_proof_matrix.py").exists(), "src exists")
    r = build_proof_matrix()
    c(r is not None,"result generated")
    c(r["proven_count"]>=6,"proven tracked")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
