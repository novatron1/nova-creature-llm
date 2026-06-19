#!/usr/bin/env python3
"""Check v102_emergency_stop."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v102_emergency_stop import verify_emergency_stop
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v102 -- Checker\n")
    c(Path(ROOT/"src"/"v102_emergency_stop.py").exists(), "src exists")
    r = verify_emergency_stop(())
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    c(r['blocks_movement'], f"blocks movement when missing")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
