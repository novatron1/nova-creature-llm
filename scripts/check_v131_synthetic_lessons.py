#!/usr/bin/env python3
"""Check v131_synthetic_lessons."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v131_synthetic_lesson_generator import generate_synthetic_lessons
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v131_synthetic_lessons -- Checker\n")
    c(Path(ROOT/"src"/"v131_synthetic_lesson_generator.py").exists(), "src exists")
    r = generate_synthetic_lessons("test",1)
    c(r is not None, "result generated")
    c(r['all_require_critic_approval'], "critic approval required")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
