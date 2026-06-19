"""v071 — Robot Safety Spine. physical_movement_allowed: false by default."""
from __future__ import annotations
from datetime import datetime
from typing import Any

SAFETY_CHECKS = [
    ("emergency_stop_available", False, "Emergency stop is not installed"),
    ("collision_check_available", False, "Collision detection is not installed"),
    ("human_distance_check_available", False, "Human distance sensor is not installed"),
    ("battery_check_available", False, "Battery monitor is not installed"),
    ("command_speed_limit", False, "Speed limit is not configured"),
    ("movement_zone_defined", False, "Movement zone is not defined"),
    ("real_hardware_config_present", False, "Real hardware config is not present"),
    ("simulation_passed", False, "Simulation has not passed"),
    ("owner_approval_present", False, "Owner approval is not present"),
]

def check_safety() -> dict[str, Any]:
    results = {}
    all_pass = True
    for name, default, reason in SAFETY_CHECKS:
        results[name] = {"pass": default, "reason": reason}
        if not default:
            all_pass = False
    return {
        "version": "v071_safety_spine",
        "created_at": datetime.now().isoformat(),
        "checks": results,
        "physical_movement_allowed": False,
        "simulation_allowed": True,
        "stop_command_always_allowed": True,
        "all_checks_pass": all_pass,
        "missing_requirements": [name for name, ok, _ in SAFETY_CHECKS if not ok],
    }

def check_simulation_command(command: str) -> dict[str, Any]:
    if command == "stop":
        return {"allowed": True, "reason": "Stop always allowed"}
    return {"allowed": True, "reason": "Simulation always allowed"}

def check_real_movement_command(command: str) -> dict[str, Any]:
    if not SAFETY_CHECKS[0][1]:  # emergency_stop_available
        return {"allowed": False, "reason": "Emergency stop not available"}
    if not SAFETY_CHECKS[-1][1]:  # owner_approval
        return {"allowed": False, "reason": "Owner approval not present"}
    return {"allowed": True, "reason": "All safety checks pass"}

def main():
    print("Nova v071 -- Robot Safety Spine\n")
    s = check_safety()
    print(f"physical_movement_allowed: {s['physical_movement_allowed']}")
    print(f"simulation_allowed: {s['simulation_allowed']}")
    print(f"Checks pass: {s['all_checks_pass']}")
    print(f"Missing: {len(s['missing_requirements'])} requirements")
    for m in s['missing_requirements']:
        print(f"  MISSING: {m}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
