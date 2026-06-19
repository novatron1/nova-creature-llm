#!/usr/bin/env python3
"""Check v126_teaching_mode."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v126_teaching_mode import explain_topic
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v126_teaching_mode -- Checker\n")
    c(Path(ROOT/"src"/"v126_teaching_mode.py").exists(), "src exists")
    r = explain_topic("test")
    c(r is not None, "result generated")
    c(len(r.get('steps',[])) >= 2, "teaching steps defined")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
