#!/usr/bin/env python3
"""Check v188_capability_proof_lab."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v188_capability_proof_lab import prove_capability, prove_from_gold
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v188_capability_proof_lab -- Checker\n")
    c(Path(ROOT/"src"/"v188_capability_proof_lab.py").exists(), "src exists")
    r = prove_capability("arithmetic")
    c(r is not None, "result generated")
    c(r["promote_allowed"], "promote allowed")
    rg = prove_from_gold()
    c(len(rg["proven"]) >= 2, "gold examples proven")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
