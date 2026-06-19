#!/usr/bin/env python3
"""Check v123_timing_brain."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v123_conversation_timing_brain import decide_timing
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v123_timing_brain -- Checker\n")
    c(Path(ROOT/"src"/"v123_conversation_timing_brain.py").exists(), "src exists")
    r = decide_timing("test")
    c(r is not None, "result generated")
    c('decision' in r, "timing decision made")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
