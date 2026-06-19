#!/usr/bin/env python3
"""Check v104_safe_zone."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v104_safe_zone import build_safe_zone_map
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v104 -- Checker\n")
    c(Path(ROOT/"src"/"v104_safe_zone.py").exists(), "src exists")
    r = build_safe_zone_map(())
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    c(r['movement_blocked'], f"movement blocked by default")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
