#!/usr/bin/env python3
"""Check v145_project_memory."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v145_long_term_project_memory import get_project_state, record_patch
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v145_project_memory -- Checker\n")
    c(Path(ROOT/"src"/"v145_long_term_project_memory.py").exists(), "src exists")
    s = get_project_state()
    c(s is not None, "state loaded")
    c("project" in s, "project name tracked")
    record_patch("v145","test")
    c(True, "patch recorded")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
