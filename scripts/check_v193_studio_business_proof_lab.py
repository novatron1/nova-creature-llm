#!/usr/bin/env python3
"""Check v193_studio_business_proof_lab."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v193_studio_business_proof_lab import run_studio_proofs
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v193_studio_business_proof_lab -- Checker\n")
    c(Path(ROOT/"src"/"v193_studio_business_proof_lab.py").exists(), "src exists")
    r = run_studio_proofs()
    c(r is not None,"result generated")
    c(r["proven"],"studio proven")
    c(r["total"]>=3,"multiple capabilities")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
