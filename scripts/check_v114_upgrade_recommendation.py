#!/usr/bin/env python3
"""Check v114_upgrade_recommendation."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v114_upgrade_recommendation_engine import recommend_next_upgrade
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v114_upgrade_recommendation -- Checker\n")
    c(Path(ROOT/"src"/"v114_upgrade_recommendation_engine.py").exists(), "src exists")
    r = recommend_next_upgrade()
    c(r is not None, "result generated")
    c(len(r.get('upgrades',[])) >= 3, "upgrades listed")
    c(r.get('selected') is not None, "recommendation made")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
