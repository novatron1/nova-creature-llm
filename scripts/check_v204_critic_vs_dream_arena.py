#!/usr/bin/env python3
"""Check v204_critic_vs_dream_arena."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v204_critic_vs_dream_arena import run_arena
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v204_critic_vs_dream_arena -- Checker\n")
    c(Path(ROOT/"src"/"v204_critic_vs_dream_arena.py").exists(), "src exists")
    r = run_arena()
    c(r is not None,"result generated")
    c(r["critic_always_wins"],"critic wins")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
