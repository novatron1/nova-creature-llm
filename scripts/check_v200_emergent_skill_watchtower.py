#!/usr/bin/env python3
"""Check v200_emergent_skill_watchtower."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v200_emergent_skill_watchtower import watch_for_skills
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v200_emergent_skill_watchtower -- Checker\n")
    c(Path(ROOT/"src"/"v200_emergent_skill_watchtower.py").exists(), "src exists")
    r = watch_for_skills()
    c(r is not None,"result generated")
    c(r["total"]>=8,"skills watched")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
