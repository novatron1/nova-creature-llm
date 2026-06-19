#!/usr/bin/env python3
"""Check v183_capability_hypothesis_generator."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v183_capability_hypothesis_generator import generate_capability_hypotheses
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v183_capability_hypothesis_generator -- Checker\n")
    c(Path(ROOT/"src"/"v183_capability_hypothesis_generator.py").exists(), "src exists")
    r = generate_capability_hypotheses()
    c(r is not None, "result generated")
    c(r["total"] >= 2, f"{r["total"]} hypotheses")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
