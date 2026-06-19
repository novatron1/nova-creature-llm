#!/usr/bin/env python3
"""v071 — Gold safety spine tests."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v071_robot_safety_spine import check_safety, check_simulation_command, check_real_movement_command
E, P = [], []
def main():
    print("Nova v071 -- Gold Safety Spine Test\n")
    # A: Real hardware missing
    s = check_safety()
    if s["physical_movement_allowed"] == False:
        P.append("A: Real hardware missing -> physical movement blocked")
    else:
        E.append("A: physical movement should be false")
    # B: Emergency stop missing
    if not s["checks"]["emergency_stop_available"]["pass"]:
        P.append("B: Emergency stop missing -> movement blocked")
    else:
        E.append("B: emergency stop should be false")
    # C: Owner approval missing
    if not s["checks"]["owner_approval_present"]["pass"]:
        P.append("C: Owner approval missing -> movement blocked")
    else:
        E.append("C: owner approval should be false")
    # D: Simulation command only
    sc = check_simulation_command("move_forward")
    if sc["allowed"]:
        P.append("D: Simulation command allowed")
    else:
        E.append("D: sim command should be allowed")
    # E: Stop command
    stop = check_simulation_command("stop")
    if stop["allowed"]:
        P.append("E: Stop command always allowed")
    else:
        E.append("E: stop should be allowed")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    (ROOT/"reports"/"v071_gold_safety_spine_test.json").write_text(json.dumps({
        "version": "v071_gold_safety_spine_test", "created_at": datetime.now().isoformat(),
        "passes": len(P), "errors": len(E)}, indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
