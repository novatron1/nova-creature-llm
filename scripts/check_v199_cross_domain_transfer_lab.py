#!/usr/bin/env python3
"""Check v199_cross_domain_transfer_lab."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v199_cross_domain_transfer_lab import run_transfer_lab
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v199_cross_domain_transfer_lab -- Checker\n")
    c(Path(ROOT/"src"/"v199_cross_domain_transfer_lab.py").exists(), "src exists")
    r = run_transfer_lab()
    c(r is not None,"result generated")
    c(r["total"]>=3,"transfers mapped")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
