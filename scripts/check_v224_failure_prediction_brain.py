#!/usr/bin/env python3
"""Check v224_failure_prediction_brain."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v224_failure_prediction_brain import predict_failures
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v224_failure_prediction_brain -- Checker\n")
    c(Path(ROOT/"src"/"v224_failure_prediction_brain.py").exists(), "src exists")
    r = predict_failures()
    c(r is not None,"result generated")
    c(r["overall_risk"]=="low","low risk")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
