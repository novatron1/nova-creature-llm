#!/usr/bin/env python3
"""Check v143_benchmark_history."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v143_benchmark_history_tracker import record_benchmark, get_latest_scores
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v143_benchmark_history -- Checker\n")
    c(Path(ROOT/"src"/"v143_benchmark_history_tracker.py").exists(), "src exists")
    r = record_benchmark("v095","test",100)
    c(r is not None, "recorded")
    latest = get_latest_scores()
    c(isinstance(latest, dict), "scores readable")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
