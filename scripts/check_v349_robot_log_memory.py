#!/usr/bin/env python3
"""Check v349_robot_log_memory."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v349_robot_log_memory import get_robot_log_memory
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v349_robot_log_memory -- Checker\n")
    c(Path(ROOT/"src"/"v349_robot_log_memory.py").exists(), "src exists")
    r = get_robot_log_memory()
    c(r is not None, "result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
