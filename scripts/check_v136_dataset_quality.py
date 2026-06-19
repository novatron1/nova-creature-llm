#!/usr/bin/env python3
"""Check v136_dataset_quality."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v136_dataset_quality_scorer import score_lesson
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v136_dataset_quality -- Checker\n")
    c(Path(ROOT/"src"/"v136_dataset_quality_scorer.py").exists(), "src exists")
    r = score_lesson("test lesson","test_role")
    c(r is not None, "result generated")
    c(not r.get('training_ready'), "not training ready without approval")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
