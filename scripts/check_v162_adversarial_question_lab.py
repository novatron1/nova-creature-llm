#!/usr/bin/env python3
"""Check v162_adversarial_question_lab."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v162_adversarial_question_lab import generate_trap_questions
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v162_adversarial_question_lab -- Checker\n")
    c(Path(ROOT/"src"/"v162_adversarial_question_lab.py").exists(), "src exists")
    r = generate_trap_questions()
    c(r is not None, "result generated")
    c(r["total"] >= 6, f"{r["total"]} traps")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
