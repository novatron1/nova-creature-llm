#!/usr/bin/env python3
"""Check v159_role_brain_sparring."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v159_role_brain_sparring import run_sparring_match
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v159_role_brain_sparring -- Checker\n")
    c(Path(ROOT/"src"/"v159_role_brain_sparring.py").exists(), "src exists")
    r = run_sparring_match("test topic")
    c(r is not None, "result generated")
    c(r["total_pairs"] >= 4, f"{r["total_pairs"]} sparring pairs")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
