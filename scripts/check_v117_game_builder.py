#!/usr/bin/env python3
"""Check v117_game_builder."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v117_game_builder_brain import game_builder_assist
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v117_game_builder -- Checker\n")
    c(Path(ROOT/"src"/"v117_game_builder_brain.py").exists(), "src exists")
    r = game_builder_assist("test")
    c(r is not None, "result generated")
    c(len(r.get('capabilities',[])) >= 3, "capabilities defined")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
