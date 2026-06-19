#!/usr/bin/env python3
"""Check v214_long_memory_recall_ladder."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v214_long_memory_recall_ladder import run_recall_ladder
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v214_long_memory_recall_ladder -- Checker\n")
    c(Path(ROOT/"src"/"v214_long_memory_recall_ladder.py").exists(), "src exists")
    r = run_recall_ladder()
    c(r is not None,"result generated")
    c(r["all_recalled"],"all recalled")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
