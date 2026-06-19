#!/usr/bin/env python3
"""Check v205_memory_pollution_defense."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v205_memory_pollution_defense import check_pollution
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v205_memory_pollution_defense -- Checker\n")
    c(Path(ROOT/"src"/"v205_memory_pollution_defense.py").exists(), "src exists")
    r = check_pollution("unapproved personal memory")
    c(r is not None,"result generated")
    c(r["blocked"],"blocks pollution")
    r2 = check_pollution("approved lesson")
    c(not r2["blocked"],"allows clean")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
