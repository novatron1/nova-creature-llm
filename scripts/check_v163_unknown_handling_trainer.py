#!/usr/bin/env python3
"""Check v163_unknown_handling_trainer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v163_unknown_handling_trainer import train_unknown, get_unknown_scenarios
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v163_unknown_handling_trainer -- Checker\n")
    c(Path(ROOT/"src"/"v163_unknown_handling_trainer.py").exists(), "src exists")
    r = train_unknown()
    c(r is not None, "result generated")
    c(r["does_not_guess"], "does not guess")
    sc = get_unknown_scenarios()
    c(len(sc) >= 3, "scenarios available")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
