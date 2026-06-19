#!/usr/bin/env python3
"""Check v203_brain_role_capability_map_v2."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v203_brain_role_capability_map_v2 import build_role_map
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v203_brain_role_capability_map_v2 -- Checker\n")
    c(Path(ROOT/"src"/"v203_brain_role_capability_map_v2.py").exists(), "src exists")
    r = build_role_map()
    c(r is not None,"result generated")
    c(r["total_roles"]==7,"7 roles mapped")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
