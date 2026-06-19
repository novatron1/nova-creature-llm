#!/usr/bin/env python3
"""Check v196_safety_blocking_amplifier."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v196_safety_blocking_amplifier import amplify_safety
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v196_safety_blocking_amplifier -- Checker\n")
    c(Path(ROOT/"src"/"v196_safety_blocking_amplifier.py").exists(), "src exists")
    r = amplify_safety()
    c(r is not None,"result generated")
    c("real_robot_movement" in r["block_rules"],"robot blocked")
    c(r["all_blocks_active"],"all active")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
