#!/usr/bin/env python3
"""Check v112_auto_learning_scheduler."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v112_auto_learning_scheduler import propose_learning_schedule
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v112_auto_learning_scheduler -- Checker\n")
    c(Path(ROOT/"src"/"v112_auto_learning_scheduler.py").exists(), "src exists")
    r = propose_learning_schedule()
    c(r is not None, "result generated")
    c(r['dry_run'], "dry-run mode active")
    c(len(r.get('proposals',[])) >= 2, "proposals listed")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
