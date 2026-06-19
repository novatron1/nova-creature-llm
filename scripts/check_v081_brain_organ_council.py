#!/usr/bin/env python3
"""Check v081 brain council."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v081_brain_organ_council import run_council
E,P=[], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v081 -- Council Checker\n")
    c((ROOT/"src"/"v081_brain_organ_council.py").exists(), "src exists")
    r = run_council("Should Nova enable real robot movement now?")
    c(len(r["role_views"]) >= 6, f">=6 roles ({len(r['role_views'])})")
    c(len(r["agreements"]) >= 2, f"agreements: {len(r['agreements'])}")
    c(len(r["blocked_actions"]) >= 1, f"blocked: {len(r['blocked_actions'])}")
    c("simulation" in r["final_recommendation"].lower(), "simulation recommended")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p_ in P: print(p_)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
