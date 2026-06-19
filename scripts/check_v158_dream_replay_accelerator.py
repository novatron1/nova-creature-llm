#!/usr/bin/env python3
"""Check v158_dream_replay_accelerator."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v158_dream_replay_accelerator import generate_dream_variants
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v158_dream_replay_accelerator -- Checker\n")
    c(Path(ROOT/"src"/"v158_dream_replay_accelerator.py").exists(), "src exists")
    r = generate_dream_variants()
    c(r is not None, "result generated")
    c(r["total_variants"] >= 40, f"{r["total_variants"]} variants")
    c(r["approved"] > 0, "some approved")
    c(r["raw_dreams_never_train"], "raw dreams blocked")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
