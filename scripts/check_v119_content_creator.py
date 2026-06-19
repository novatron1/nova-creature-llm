#!/usr/bin/env python3
"""Check v119_content_creator."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v119_content_creator_brain import content_creator_assist
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v119_content_creator -- Checker\n")
    c(Path(ROOT/"src"/"v119_content_creator_brain.py").exists(), "src exists")
    r = content_creator_assist("test")
    c(r is not None, "result generated")
    c(len(r.get('capabilities',[])) >= 3, "capabilities defined")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
