#!/usr/bin/env python3
"""Check v142_dataset_growth."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v142_dataset_growth_engine import classify_lesson, get_dataset_stats
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v142_dataset_growth -- Checker\n")
    c(Path(ROOT/"src"/"v142_dataset_growth_engine.py").exists(), "src exists")
    e = classify_lesson("v086 reasoning passed", "test")
    c(e is not None, "lesson classified")
    c("classification" in e, "has classification")
    stats = get_dataset_stats()
    c(isinstance(stats, dict), "stats readable")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
