"""v071 — Robot Safety Spine

Safety approval layer for robot movement.
Physical movement is DISABLED by default.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def root() -> Path:
    return ROOT


def default_safety_state() -> dict[str, Any]:
    return {
        "version": "v071_robot_safety_spine",
        "created_at": datetime.now().isoformat(),
        "checks": {
            "emergency_stop_available": {
                "status": "missing",
                "required": True,
                "note": "Emergency stop circuit must be installed and tested before any real movement",
            },
            "collision_check_available": {
                "status": "missing",
                "required": True,
                "note": "Collision detection (lidar, ultrasonic, or bumper sensors) required",
            },
            "human_distance_check_available": {
                "status": "missing",
                "required": True,
                "note": "Human proximity detection required for safe operation near people",
            },
            "battery_check_available": {
                "status": "missing",
                "required": True,
                "note": "Battery voltage monitoring required to prevent low-power runaway",
            },
            "command_speed_limit": {
                "status": "defined",
                "required": True,
                "note": "Speed limited to 0.5 m/s in simulation, must be enforced in real mode",
            },
            "movement_zone_defined": {
                "status": "missing",
                "required": True,
                "note": "Physical movement boundaries must be configured",
            },
            "real_hardware_config_present": {
                "status": "missing",
                "required": True,
                "note": "Real hardware configuration file must exist and be validated",
            },
            "simulation_passed": {
                "status": "pending",
                "required": True,
                "note": "Full simulation test suite must pass before real movement",
            },
            "manual_owner_approval_required": {
                "status": "pending",
                "required": True,
                "note": "Human owner must explicitly approve real robot operation",
            },
        },
        "physical_movement_allowed": False,
        "simulation_allowed": True,
        "decision": "BLOCKED — physical movement is disabled by default",
        "unblock_requirements": [
            "Install and test emergency stop hardware",
            "Install collision detection sensors",
            "Install human proximity detection",
            "Install battery monitor",
            "Define movement zone boundaries",
            "Create real hardware configuration file",
            "Pass full simulation test suite",
            "Obtain manual owner approval",
        ],
        "note": "v071 defines the safety spine. Real robot movement requires all checks to pass.",
    }


def run_safety_checks() -> dict[str, Any]:
    """Run all safety checks and return current state."""
    state = default_safety_state()
    checks = state["checks"]

    # Check if any real hardware config exists
    config_files = list((root() / "config").glob("*robot*")) if (root() / "config").exists() else []
    config_files += list((root() / "config").glob("*hardware*")) if (root() / "config").exists() else []
    if config_files:
        checks["real_hardware_config_present"]["status"] = "present"
        checks["real_hardware_config_present"]["files"] = [str(f.relative_to(root())) for f in config_files]

    # Check if simulation has been run
    sim_log = root() / "data" / "robot_sim" / "simulation_log.jsonl"
    if sim_log.exists() and sim_log.stat().st_size > 0:
        checks["simulation_passed"]["status"] = "passed"
        checks["simulation_passed"]["note"] = "Simulation log exists with recorded runs"

    # Check if v070 sim bridge is installed
    if (root() / "src" / "v070_robot_sim_bridge.py").exists():
        checks["simulation_passed"]["state"] = "v070_bridge_installed"

    # Overall decision
    all_required = all(
        ch["status"] in ("present", "passed", "defined", "installed")
        for ch in checks.values()
    )
    state["physical_movement_allowed"] = all_required
    state["decision"] = (
        "APPROVED — all safety checks passed"
        if all_required
        else "BLOCKED — physical movement requires all safety checks to pass"
    )

    return state


def check_physical_movement_allowed() -> bool:
    state = run_safety_checks()
    return state["physical_movement_allowed"]


def check_simulation_allowed() -> bool:
    state = run_safety_checks()
    return state.get("simulation_allowed", True)


def get_blockers() -> list[str]:
    state = run_safety_checks()
    blockers = []
    for name, ch in state["checks"].items():
        if ch["status"] not in ("present", "passed", "defined", "installed"):
            blockers.append(f"{name}: {ch['status']} — {ch['note']}")
    return blockers


def save_report(report: dict[str, Any] | None = None) -> Path:
    if report is None:
        report = run_safety_checks()
    reports_dir = root() / "reports"
    reports_dir.mkdir(exist_ok=True)
    path = reports_dir / "v071_robot_safety_spine_report.json"
    path.write_text(json.dumps(report, indent=2))
    return path


def main() -> int:
    state = run_safety_checks()
    save_report(state)

    print("Nova Creature v071 — Robot Safety Spine\n")
    print(f"Physical movement allowed: {state['physical_movement_allowed']}")
    print(f"Simulation allowed: {state['simulation_allowed']}")
    print(f"Decision: {state['decision']}\n")

    print("Safety checks:")
    for name, ch in state["checks"].items():
        icon = {"present": "✅", "passed": "✅", "defined": "✅", "installed": "✅",
                "missing": "❌", "pending": "⏳"}.get(ch["status"], "❓")
        print(f"  {icon} {name}: {ch['status']}")
        print(f"     {ch['note']}")

    print("\nUnblock requirements:")
    for i, req in enumerate(state["unblock_requirements"], 1):
        print(f"  {i}. {req}")

    print(f"\nReport: reports/v071_robot_safety_spine_report.json")
    return 0 if not state["physical_movement_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
