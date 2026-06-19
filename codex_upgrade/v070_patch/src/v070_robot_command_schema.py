"""v070 — Robot Command Schema

Defines the command format for robot actions.
All commands are simulation-only in v070.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

SUPPORTED_COMMANDS = {
    "stop": {
        "description": "Emergency stop — halt all movement immediately",
        "parameters": [],
        "safety_check_required": True,
        "always_allowed": True,
    },
    "look_left": {
        "description": "Turn visual sensor left",
        "parameters": [{"name": "degrees", "type": "int", "default": 30, "min": 0, "max": 180}],
        "safety_check_required": True,
        "always_allowed": False,
    },
    "look_right": {
        "description": "Turn visual sensor right",
        "parameters": [{"name": "degrees", "type": "int", "default": 30, "min": 0, "max": 180}],
        "safety_check_required": True,
        "always_allowed": False,
    },
    "scan_room": {
        "description": "Scan the room with available sensors",
        "parameters": [],
        "safety_check_required": True,
        "always_allowed": False,
    },
    "move_forward": {
        "description": "Move forward a distance",
        "parameters": [{"name": "distance_cm", "type": "int", "default": 10, "min": 1, "max": 100}],
        "safety_check_required": True,
        "always_allowed": False,
    },
    "move_backward": {
        "description": "Move backward a distance",
        "parameters": [{"name": "distance_cm", "type": "int", "default": 10, "min": 1, "max": 50}],
        "safety_check_required": True,
        "always_allowed": False,
    },
    "turn_left": {
        "description": "Turn left by degrees",
        "parameters": [{"name": "degrees", "type": "int", "default": 90, "min": 1, "max": 360}],
        "safety_check_required": True,
        "always_allowed": False,
    },
    "turn_right": {
        "description": "Turn right by degrees",
        "parameters": [{"name": "degrees", "type": "int", "default": 90, "min": 1, "max": 360}],
        "safety_check_required": True,
        "always_allowed": False,
    },
    "return_home": {
        "description": "Return to starting position",
        "parameters": [],
        "safety_check_required": True,
        "always_allowed": False,
    },
    "speak": {
        "description": "Speak a phrase through speaker",
        "parameters": [{"name": "phrase", "type": "string", "default": "Hello"}],
        "safety_check_required": False,
        "always_allowed": True,
    },
}


def create_command(
    command: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a robot command record."""
    if command not in SUPPORTED_COMMANDS:
        cmd_info = SUPPORTED_COMMANDS.get(command)
        if not cmd_info:
            return {"ok": False, "error": f"Unknown command: {command}"}

    cmd_info = SUPPORTED_COMMANDS[command]
    resolved_params = {}
    if parameters:
        for param_def in cmd_info["parameters"]:
            name = param_def["name"]
            if name in parameters:
                value = parameters[name]
                if "min" in param_def and value < param_def["min"]:
                    return {"ok": False, "error": f"{name} below minimum ({param_def['min']})"}
                if "max" in param_def and value > param_def["max"]:
                    return {"ok": False, "error": f"{name} above maximum ({param_def['max']})"}
                resolved_params[name] = value
            else:
                resolved_params[name] = param_def["default"]

    return {
        "ok": True,
        "command": command,
        "parameters": resolved_params,
        "description": cmd_info["description"],
        "requires_safety_check": cmd_info["safety_check_required"],
        "always_allowed": cmd_info["always_allowed"],
        "timestamp": datetime.now().isoformat(),
    }


def get_schema_summary() -> dict[str, Any]:
    return {
        "version": "v070_robot_command_schema",
        "total_commands": len(SUPPORTED_COMMANDS),
        "commands": {k: {"description": v["description"][:50], "safety_required": v["safety_check_required"]} for k, v in SUPPORTED_COMMANDS.items()},
    }
