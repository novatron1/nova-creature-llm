#!/usr/bin/env python3
"""Check v218_reasoning_step_quality_scorer."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v218_reasoning_step_quality_scorer import score_reasoning
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v218_reasoning_step_quality_scorer -- Checker\n")
    c(Path(ROOT/"src"/"v218_reasoning_step_quality_scorer.py").exists(), "src exists")
    r = score_reasoning()
    c(r is not None,"result generated")
    c(r["quality_score"]>=50,"quality scored")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
