#!/usr/bin/env python3
"""Check v129_glasses_mode."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v129_short_answer_glasses_mode import glasses_answer
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v129_glasses_mode -- Checker\n")
    c(Path(ROOT/"src"/"v129_short_answer_glasses_mode.py").exists(), "src exists")
    r = glasses_answer("test")
    c(r is not None, "result generated")
    c(r.get('no_long_code'), "no long code")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
