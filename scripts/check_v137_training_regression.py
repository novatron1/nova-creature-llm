#!/usr/bin/env python3
"""Check v137_training_regression."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v137_training_regression_detector import detect_training_regression
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v137_training_regression -- Checker\n")
    c(Path(ROOT/"src"/"v137_training_regression_detector.py").exists(), "src exists")
    r = detect_training_regression({"a":90},{"a":85})
    c(r is not None, "result generated")
    c(r['regression_detected'], "regression detected")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
