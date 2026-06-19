#!/usr/bin/env python3
"""Check v130_deep_research."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v130_deep_research_mode import deep_research
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v130_deep_research -- Checker\n")
    c(Path(ROOT/"src"/"v130_deep_research_mode.py").exists(), "src exists")
    r = deep_research("test")
    c(r is not None, "result generated")
    c(r.get('decomposed'), "decomposes questions")
    c(r.get('unsupported_claims_avoided'), "no unsupported claims")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
