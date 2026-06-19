#!/usr/bin/env python3
"""Check v173_long_context_challenge_builder."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v173_long_context_challenge_builder import build_challenges
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v173_long_context_challenge_builder -- Checker\n")
    c(Path(ROOT/"src"/"v173_long_context_challenge_builder.py").exists(), "src exists")
    r = build_challenges()
    c(r is not None, "result generated")
    c(r["total"] >= 3, f"{r["total"]} challenges")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
