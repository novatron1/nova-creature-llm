#!/usr/bin/env python3
"""Check v147_checkpoint_tournament."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v147_checkpoint_tournament import run_tournament
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v147_checkpoint_tournament -- Checker\n")
    c(Path(ROOT/"src"/"v147_checkpoint_tournament.py").exists(), "src exists")
    r = run_tournament()
    c(r is not None, "result generated")
    c(r.get("winner") is not None, "winner selected")
    c(r["winner"]["name"] == "v055_current", "current checkpoint wins")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
