#!/usr/bin/env python3
"""Check v235_planner_candidate_checkpoint_builder."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v235_planner_candidate_checkpoint_builder import build_checkpoint
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v235_planner_candidate_checkpoint_builder -- Checker\n")
    c(Path(ROOT/"src"/"v235_planner_candidate_checkpoint_builder.py").exists(), "src exists")
    r = build_checkpoint()
    c(r is not None,"result generated")
    c(r["v055_preserved"],"v055 preserved")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
