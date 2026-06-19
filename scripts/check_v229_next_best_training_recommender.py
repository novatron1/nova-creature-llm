#!/usr/bin/env python3
"""Check v229_next_best_training_recommender."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v229_next_best_training_recommender import recommend_training
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v229_next_best_training_recommender -- Checker\n")
    c(Path(ROOT/"src"/"v229_next_best_training_recommender.py").exists(), "src exists")
    r = recommend_training()
    c(r is not None,"result generated")
    c("next_best_role" in r,"recommendation made")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
