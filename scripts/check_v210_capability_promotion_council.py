#!/usr/bin/env python3
"""Check v210_capability_promotion_council."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v210_capability_promotion_council import decide_promotion
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v210_capability_promotion_council -- Checker\n")
    c(Path(ROOT/"src"/"v210_capability_promotion_council.py").exists(), "src exists")
    r = decide_promotion("arithmetic",True,True,True)
    c(r is not None,"result generated")
    c(r["promote"],"promotes when ready")
    r2 = decide_promotion("fake",False,False,False)
    c(not r2["promote"],"blocks when not ready")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
