#!/usr/bin/env python3
"""Check v346_robot_simulation_certification."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v346_robot_simulation_certification import get_simulation_certification
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v346_robot_simulation_certification -- Checker\n")
    c(Path(ROOT/"src"/"v346_robot_simulation_certification.py").exists(), "src exists")
    r = get_simulation_certification()
    c(r is not None, "result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
