#!/usr/bin/env python3
"""Check v226_synthetic_teacher_loop."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v226_synthetic_teacher_loop import run_teacher_loop
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v226_synthetic_teacher_loop -- Checker\n")
    c(Path(ROOT/"src"/"v226_synthetic_teacher_loop.py").exists(), "src exists")
    r = run_teacher_loop()
    c(r is not None,"result generated")
    c(r["teacher_active"],"teacher active")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
