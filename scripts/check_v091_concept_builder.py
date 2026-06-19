#!/usr/bin/env python3
"""Check check_v091_concept_builder."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v091_concept_builder import build_concept
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v091 -- Checker\n")
    c(True, "src module exists")
    build_concept("benchmark advancement", ["improves score", "preserves old tests"], ["adds files but no test"])
    r = build_concept("benchmark advancement", ["improves score", "preserves old tests"], ["adds files but no test"])
    if isinstance(r, tuple):
        r = r[0]

    c(len(r['examples']) >= 2, f">=2 examples")

    c('pattern' in r, f"pattern present")

    c('rule' in r, f"rule present")

    c('boundary' in r, f"boundary present")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
