#!/usr/bin/env python3
"""Check v213_project_continuity_marathon."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v213_project_continuity_marathon import run_continuity_marathon
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v213_project_continuity_marathon -- Checker\n")
    c(Path(ROOT/"src"/"v213_project_continuity_marathon.py").exists(), "src exists")
    r = run_continuity_marathon()
    c(r is not None,"result generated")
    c(r["all_passed"],"all continuity passes")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
