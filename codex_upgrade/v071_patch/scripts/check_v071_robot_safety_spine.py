from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v071_robot_safety_spine import (
    run_safety_checks, check_physical_movement_allowed,
    check_simulation_allowed, get_blockers,
)

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v071 — Robot Safety Spine Checker\n")

    # Files exist
    for f in [ROOT/"src"/"v071_robot_safety_spine.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # Run safety checks
    state = run_safety_checks()

    # Physical movement blocked by default
    check(not state["physical_movement_allowed"], "physical movement is BLOCKED by default")
    check(state["simulation_allowed"], "simulation IS allowed")

    # All required checks are present
    check(len(state["checks"]) == 9, f"9 safety checks ({len(state['checks'])})")
    for name, ch in state["checks"].items():
        check("status" in ch and "required" in ch and "note" in ch,
              f"{name} has required fields")

    # Emergency stop is required
    es = state["checks"].get("emergency_stop_available", {})
    check(es.get("required"), "emergency_stop is required")
    check(es.get("status") == "missing", "emergency_stop is missing by default")

    # Owner approval required
    oa = state["checks"].get("manual_owner_approval_required", {})
    check(oa.get("required"), "owner approval is required")

    # Blockers
    blockers = get_blockers()
    check(len(blockers) >= 5, f"{len(blockers)} blockers identified")

    # Functions
    check(not check_physical_movement_allowed(), "check_physical_movement_allowed returns False")
    check(check_simulation_allowed(), "check_simulation_allowed returns True")

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(f"  ❌ {e}")

    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
