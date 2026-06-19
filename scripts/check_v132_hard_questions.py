#!/usr/bin/env python3
"""Check v132_hard_questions."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v132_hard_question_generator import generate_hard_questions
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v132_hard_questions -- Checker\n")
    c(Path(ROOT/"src"/"v132_hard_question_generator.py").exists(), "src exists")
    r = generate_hard_questions("test",1)
    c(r is not None, "result generated")
    c(len(r.get('questions',[])) >= 1, "questions generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
