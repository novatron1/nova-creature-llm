#!/usr/bin/env python3
"""Check v115_studio_business."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v115_studio_business_assistant import studio_assist
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v115_studio_business -- Checker\n")
    c(Path(ROOT/"src"/"v115_studio_business_assistant.py").exists(), "src exists")
    r = studio_assist("test")
    c(r is not None, "result generated")
    c(len(r.get('capabilities',[])) >= 3, "capabilities defined")
    c(r.get('simulation_only'), "simulation only")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
