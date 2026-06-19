#!/usr/bin/env python3
"""Check v071 safety spine."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v071_robot_safety_spine import check_safety, check_simulation_command, check_real_movement_command
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  \u2705 {msg}")
    else: E.append(f"  \u274c {msg}")
def main():
    print("Nova v071 -- Safety Spine Checker\n")
    c(Path(ROOT/"src"/"v071_robot_safety_spine.py").exists(), "src exists")
    s = check_safety()
    c(s["physical_movement_allowed"] == False, "physical movement blocked")
    c(s["simulation_allowed"] == True, "simulation allowed")
    c(s["stop_command_always_allowed"] == True, "stop always allowed")
    c(s["all_checks_pass"] == False, "checks not all pass (default)")
    c(len(s["missing_requirements"]) >= 8, f"{len(s['missing_requirements'])} missing reqs")
    sc = check_simulation_command("move_forward")
    c(sc["allowed"], "sim command allowed")
    rc = check_real_movement_command("move_forward")
    c(rc["allowed"] == False, "real movement blocked without safety")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
