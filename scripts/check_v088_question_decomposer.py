#!/usr/bin/env python3
"""Check check_v088_question_decomposer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v088_question_decomposer import decompose_question
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v088 -- Checker\n")
    c(True, "src module exists")
    decompose_question("Can it run a robot and write scripts and know what it can do?")
    r = decompose_question("Can it run a robot and write scripts and know what it can do?")
    if isinstance(r, tuple):
        r = r[0]

    c(len(r['subquestions']) >= 3, f">=3 subquestions")

    c(len(r['route_for_each_subquestion']) >= 3, f"routes for subqs")

    c(isinstance(r['ambiguity_flags'], list), f"ambiguity flags list")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
