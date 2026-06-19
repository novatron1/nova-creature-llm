#!/usr/bin/env python3
"""Check v156_weakness_targeted_lessons."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v156_weakness_targeted_lessons import generate_weakness_lessons, get_weakness_report
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v156_weakness_targeted_lessons -- Checker\n")
    c(Path(ROOT/"src"/"v156_weakness_targeted_lessons.py").exists(), "src exists")
    r = generate_weakness_lessons("unknown_handling",50)
    c(r is not None, "result generated")
    c(len(r["lessons"]) >= 1, "lessons created")
    wr = get_weakness_report()
    c(len(wr["known_weaknesses"]) >= 2, "weakness report available")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
