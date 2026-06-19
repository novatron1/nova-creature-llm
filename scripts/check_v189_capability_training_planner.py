#!/usr/bin/env python3
"""Check v189_capability_training_planner."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v189_capability_training_planner import plan_training_for_capability
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v189_capability_training_planner -- Checker\n")
    c(Path(ROOT/"src"/"v189_capability_training_planner.py").exists(), "src exists")
    r = plan_training_for_capability({"capability_name":"arithmetic","blocked":False},{"proven":True})
    c(r is not None, "result generated")
    c(r["train_or_block"] == "train", "allows training")
    r2 = plan_training_for_capability({"capability_name":"real_robot_movement","blocked":True},{"proven":False})
    c(r2["train_or_block"] == "block", "blocks risky")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
