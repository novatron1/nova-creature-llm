#!/usr/bin/env python3
"""Check v672 — v055 Champion Profile"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v672_v055_champion_profile import get_v055_champion_profile

E, P = [], []

def c(cond, msg):
    if cond:
        P.append(f"  [PASS] {msg}")
    else:
        E.append(f"  [FAIL] {msg}")

def main():
    print(f"Nova v672_v055_champion_profile -- Checker\n")
    c(Path(ROOT / "src" / "v672_v055_champion_profile.py").exists(), "src exists")
    r = get_v055_champion_profile()
    c(r is not None, "result generated")
    c(isinstance(r, dict), "result is dict")
    c(r.get("version") == "v672_v055_champion_profile", f"version field correct: {r.get('version')}")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P:
        print(p)
    for e in E:
        print(e)
    return 0 if not E else 1

if __name__ == "__main__":
    raise SystemExit(main())
