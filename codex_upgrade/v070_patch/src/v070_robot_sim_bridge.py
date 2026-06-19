"""v070 — Robot Simulation Bridge

Simulates robot commands in a virtual environment.
real_hardware_sent is always False in v070.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SIM_LOG = ROOT / "data" / "robot_sim" / "simulation_log.jsonl"


def root() -> Path:
    return ROOT


def ensure_storage() -> None:
    (ROOT / "data" / "robot_sim").mkdir(parents=True, exist_ok=True)


def simulate_command(
    command: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Simulate a robot command and return the result."""
    ensure_storage()

    sim_position = {"x": 0, "y": 0, "heading": 0}
    sim_sensors = {"obstacle_detected": False, "battery_level": 85, "temperature_c": 22}

    safety_check = {"passed": True, "checks": []}

    if command == "stop":
        safety_check["checks"].append("Stop command — always allowed")
        sim_result = "Robot stopped. All motors halted."
    elif command in ("look_left", "look_right"):
        degrees = (parameters or {}).get("degrees", 30)
        direction = "left" if command == "look_left" else "right"
        safety_check["checks"].append(f"Visual sensor turn {direction} — safe")
        sim_result = f"Camera turned {direction} by {degrees}°."
    elif command == "scan_room":
        safety_check["checks"].append("Room scan — no movement required")
        sim_result = "Room scanned. No obstacles detected in simulated range."
    elif command == "move_forward":
        dist = (parameters or {}).get("distance_cm", 10)
        safety_check["checks"].append(f"Forward {dist}cm — simulation passed (no obstacles)")
        sim_position["x"] += dist
        sim_result = f"Moved forward {dist}cm. Position: ({sim_position['x']}, {sim_position['y']})."
    elif command == "move_backward":
        dist = (parameters or {}).get("distance_cm", 10)
        safety_check["checks"].append(f"Backward {dist}cm — simulation passed")
        sim_position["x"] -= dist
        sim_result = f"Moved backward {dist}cm. Position: ({sim_position['x']}, {sim_position['y']})."
    elif command in ("turn_left", "turn_right"):
        degrees = (parameters or {}).get("degrees", 90)
        direction = "left" if command == "turn_left" else "right"
        delta = degrees if command == "turn_left" else -degrees
        sim_position["heading"] = (sim_position["heading"] + delta) % 360
        safety_check["checks"].append(f"Turn {direction} {degrees}° — simulation passed")
        sim_result = f"Turned {direction} by {degrees}°. Heading: {sim_position['heading']}°."
    elif command == "return_home":
        dist = abs(sim_position["x"]) + abs(sim_position["y"])
        safety_check["checks"].append(f"Return home — path length: {dist} units — simulation passed")
        sim_position = {"x": 0, "y": 0, "heading": 0}
        sim_result = "Returned to home position."
    elif command == "speak":
        phrase = (parameters or {}).get("phrase", "Hello")
        safety_check["checks"].append("Speech output — no movement required")
        sim_result = f"Simulated speech: '{phrase}'."
    else:
        return {"ok": False, "error": f"Unknown command: {command}"}

    record = {
        "version": "v070_robot_sim_bridge",
        "event_id": f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        "created_at": datetime.now().isoformat(),
        "command": command,
        "parameters": parameters or {},
        "safety_check": safety_check,
        "simulated_result": sim_result,
        "simulated_position": sim_position,
        "simulated_sensors": sim_sensors,
        "real_hardware_sent": False,
        "note": "Simulation only — no real hardware commands were sent",
    }

    with SIM_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def get_sim_log(limit: int = 10) -> list[dict[str, Any]]:
    if not SIM_LOG.exists():
        return []
    lines = [l for l in SIM_LOG.read_text().splitlines() if l.strip()]
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def get_bridge_summary() -> dict[str, Any]:
    events = get_sim_log(limit=999)
    command_counts: dict[str, int] = {}
    for e in events:
        cmd = e.get("command", "unknown")
        command_counts[cmd] = command_counts.get(cmd, 0) + 1
    hardware_sent = any(e.get("real_hardware_sent") for e in events)
    return {
        "version": "v070_robot_sim_bridge",
        "total_simulations": len(events),
        "command_counts": command_counts,
        "real_hardware_sent_ever": hardware_sent,
        "simulation_only": True,
        "motor_control_disabled": True,
    }
