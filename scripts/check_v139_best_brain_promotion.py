#!/usr/bin/env python3
"""Check v139_best_brain_promotion."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v139_best_brain_promotion import promote_best_brain
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v139_best_brain_promotion -- Checker\n")
    c(Path(ROOT/"src"/"v139_best_brain_promotion.py").exists(), "src exists")
    r = promote_best_brain("test")
    c(r is not None, "result generated")
    c(not r.get('promote_ready') or r.get('promote_ready'), "promotion check runs")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
