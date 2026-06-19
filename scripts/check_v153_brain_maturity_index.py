#!/usr/bin/env python3
"""Check v153_brain_maturity_index."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v153_brain_maturity_index import calculate_brain_age, record_age_snapshot
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v153_brain_maturity_index -- Checker\n")
    c(Path(ROOT/"src"/"v153_brain_maturity_index.py").exists(), "src exists")
    r = calculate_brain_age()
    c(r is not None, "result generated")
    c("overall_brain_maturity" in r, "maturity scored")
    c(r["overall_brain_maturity"] >= 50, "meaningful score")
    r2 = record_age_snapshot()
    c(r2["overall_brain_maturity"] == r["overall_brain_maturity"], "snapshot recorded")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
