#!/usr/bin/env python3
"""Check v176_critic_precision_trainer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v176_critic_precision_trainer import evaluate_claim, get_test_set
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v176_critic_precision_trainer -- Checker\n")
    c(Path(ROOT/"src"/"v176_critic_precision_trainer.py").exists(), "src exists")
    r = evaluate_claim("fake robot movement","block")
    c(r is not None, "result generated")
    c(r["action_taken"] == "block", "blocks correctly")
    ts = get_test_set()
    c(len(ts) >= 3, "test set available")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
