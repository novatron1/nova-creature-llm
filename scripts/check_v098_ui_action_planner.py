#!/usr/bin/env python3
"""Check v098_ui_action_planner."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v098_ui_action_planner import plan_ui_action
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v098 -- Checker\n")
    c(Path(ROOT/"src"/"v098_ui_action_planner.py").exists(), "src exists")
    r = plan_ui_action("Screen shows v095 passed.", "Continue build.")
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
