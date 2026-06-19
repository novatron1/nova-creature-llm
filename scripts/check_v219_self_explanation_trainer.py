#!/usr/bin/env python3
"""Check v219_self_explanation_trainer."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v219_self_explanation_trainer import train_self_explanation
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v219_self_explanation_trainer -- Checker\n")
    c(Path(ROOT/"src"/"v219_self_explanation_trainer.py").exists(), "src exists")
    r = train_self_explanation()
    c(r is not None,"result generated")
    c(r["no_false_claims"],"no false claims")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
