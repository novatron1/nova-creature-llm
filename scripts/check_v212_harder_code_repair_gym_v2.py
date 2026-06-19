#!/usr/bin/env python3
"""Check v212_harder_code_repair_gym_v2."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v212_harder_code_repair_gym_v2 import generate_harder_problems
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v212_harder_code_repair_gym_v2 -- Checker\n")
    c(Path(ROOT/"src"/"v212_harder_code_repair_gym_v2.py").exists(), "src exists")
    r = generate_harder_problems()
    c(r is not None,"result generated")
    c(r["sandbox_only"],"sandbox only")
    c(r["total"]>=5,"multiple problems")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
