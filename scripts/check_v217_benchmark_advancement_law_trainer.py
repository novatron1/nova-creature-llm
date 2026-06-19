#!/usr/bin/env python3
"""Check v217_benchmark_advancement_law_trainer."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v217_benchmark_advancement_law_trainer import train_benchmark_law
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v217_benchmark_advancement_law_trainer -- Checker\n")
    c(Path(ROOT/"src"/"v217_benchmark_advancement_law_trainer.py").exists(), "src exists")
    r = train_benchmark_law()
    c(r is not None,"result generated")
    c("benchmark" in r["law"].lower(),"law defined")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
