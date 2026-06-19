#!/usr/bin/env python3
"""Check v678 — Champion History Tracker"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v678_champion_history import track_champion_history

E, P = [], []

def c(cond, msg):
    if cond:
        P.append(f"  [PASS] {msg}")
    else:
        E.append(f"  [FAIL] {msg}")

def main():
    print(f"Nova v678_champion_history -- Checker\n")
    c(Path(ROOT / "src" / "v678_champion_history.py").exists(), "src exists")
    r = track_champion_history()
    c(r is not None, "result generated")
    c(isinstance(r, dict), "result is dict")
    c(r.get("version") == "v678_champion_history", f"version field correct: {r.get('version')}")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P:
        print(p)
    for e in E:
        print(e)
    return 0 if not E else 1

if __name__ == "__main__":
    raise SystemExit(main())
