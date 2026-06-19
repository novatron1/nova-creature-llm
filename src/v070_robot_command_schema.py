"""v070 — Robot Command Schema (simulation-only)."""
from __future__ import annotations
from typing import Any

COMMAND_SCHEMA: dict[str, dict[str, Any]] = {
    "stop": {"description": "Immediate stop", "parameters": {}, "safety_check_required": False, "always_allowed": True},
    "speak": {"description": "Speak message", "parameters": {"message": {"type": "string", "required": True}}, "safety_check_required": False, "always_allowed": True},
    "scan_room": {"description": "Scan environment", "parameters": {}, "safety_check_required": False, "always_allowed": True},
    "look_left": {"description": "Look left", "parameters": {"degrees": {"type": "number", "default": 45}}, "safety_check_required": True, "always_allowed": False},
    "look_right": {"description": "Look right", "parameters": {"degrees": {"type": "number", "default": 45}}, "safety_check_required": True, "always_allowed": False},
    "move_forward": {"description": "Move forward", "parameters": {"units": {"type": "number", "default": 1.0}}, "safety_check_required": True, "always_allowed": False},
    "move_backward": {"description": "Move backward", "parameters": {"units": {"type": "number", "default": 1.0}}, "safety_check_required": True, "always_allowed": False},
    "turn_left": {"description": "Turn left", "parameters": {"degrees": {"type": "number", "default": 90}}, "safety_check_required": True, "always_allowed": False},
    "turn_right": {"description": "Turn right", "parameters": {"degrees": {"type": "number", "default": 90}}, "safety_check_required": True, "always_allowed": False},
    "return_home": {"description": "Return to start", "parameters": {}, "safety_check_required": True, "always_allowed": True},
}

def get_command(name: str) -> dict[str, Any] | None:
    return COMMAND_SCHEMA.get(name)

def list_commands() -> list[str]:
    return list(COMMAND_SCHEMA.keys())

def validate_command(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = COMMAND_SCHEMA.get(name)
    if schema is None:
        return {"valid": False, "error": f"Unknown: {name}"}
    if params is None:
        params = {}
    for pn, ps in schema["parameters"].items():
        if ps.get("required") and pn not in params:
            params[pn] = ps.get("default")
    return {"valid": True, "command": name, "params": params, "schema": schema}
