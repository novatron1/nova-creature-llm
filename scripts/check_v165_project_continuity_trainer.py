#!/usr/bin/env python3
"""Check v165_project_continuity_trainer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v165_project_continuity_trainer import test_continuity
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v165_project_continuity_trainer -- Checker\n")
    c(Path(ROOT/"src"/"v165_project_continuity_trainer.py").exists(), "src exists")
    r = test_continuity("v056-v066")
    c(r is not None, "result generated")
    c("Foundation" in r["description"], "foundation remembered")
    c(r["stacks_tracked"] >= 4, f"{r["stacks_tracked"]} stacks")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
