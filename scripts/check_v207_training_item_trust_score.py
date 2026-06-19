#!/usr/bin/env python3
"""Check v207_training_item_trust_score."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v207_training_item_trust_score import score_trust
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v207_training_item_trust_score -- Checker\n")
    c(Path(ROOT/"src"/"v207_training_item_trust_score.py").exists(), "src exists")
    r = score_trust({"text":"12*12=144","source":"verified","approval":"approved"})
    c(r is not None,"result generated")
    c(r["trust_score"]==100,"perfect score")
    r2 = score_trust({"text":"maybe","source":"unknown","approval":"pending"})
    c(r2["trust_score"]<70,"low trust")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
