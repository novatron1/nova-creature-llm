#!/usr/bin/env python3
"""Check v201_capability_claim_firewall."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v201_capability_claim_firewall import filter_claim
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v201_capability_claim_firewall -- Checker\n")
    c(Path(ROOT/"src"/"v201_capability_claim_firewall.py").exists(), "src exists")
    r = filter_claim("Nova can move a real robot.")
    c(r is not None,"result generated")
    c(r["blocked"],"blocks fake robot claim")
    r2 = filter_claim("Nova can simulate robot commands.")
    c(not r2["blocked"],"allows true sim claim")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
