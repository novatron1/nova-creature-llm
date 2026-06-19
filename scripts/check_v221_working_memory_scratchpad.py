#!/usr/bin/env python3
"""Check v221_working_memory_scratchpad."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v221_working_memory_scratchpad import use_scratchpad
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v221_working_memory_scratchpad -- Checker\n")
    c(Path(ROOT/"src"/"v221_working_memory_scratchpad.py").exists(), "src exists")
    r = use_scratchpad("12*12")
    c(r is not None,"result generated")
    c(r["scratchpad_used"],"scratchpad used")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
