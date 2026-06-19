#!/usr/bin/env python3
"""Check v135_finetune_planner."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v135_targeted_finetune_planner import plan_finetune
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v135_finetune_planner -- Checker\n")
    c(Path(ROOT/"src"/"v135_targeted_finetune_planner.py").exists(), "src exists")
    r = plan_finetune("test",["weakness"])
    c(r is not None, "result generated")
    c(r['requires_owner_approval'], "requires approval")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
