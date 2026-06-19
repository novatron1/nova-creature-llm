#!/usr/bin/env python3
"""Check v138_checkpoint_tournament."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v138_checkpoint_tournament import compare_checkpoints
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v138_checkpoint_tournament -- Checker\n")
    c(Path(ROOT/"src"/"v138_checkpoint_tournament.py").exists(), "src exists")
    r = compare_checkpoints()
    c(r is not None, "result generated")
    c(r.get('winner') is not None, "winner found")
    c(r.get('score_decides'), "score decides winner")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
