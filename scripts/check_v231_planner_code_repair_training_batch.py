#!/usr/bin/env python3
"""Check v231_planner_code_repair_training_batch."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v231_planner_code_repair_training_batch import build_planner_batch
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v231_planner_code_repair_training_batch -- Checker\n")
    c(Path(ROOT/"src"/"v231_planner_code_repair_training_batch.py").exists(), "src exists")
    r = build_planner_batch()
    c(r is not None,"result generated")
    c(r["total"]>=3,"lessons built")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
