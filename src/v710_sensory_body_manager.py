"""710 — Sensory Body Layer: Sensory Body Manager"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def sensory_body_manager():
    """Central coordinator for the sensory body system."""
    result = {"version": "v710_sensory_body_manager", "created_at": datetime.now().isoformat(),
              "components": {}, "status": "ok"}
    try:
        from v705_device_registry import device_registry
        result["components"]["device_registry"] = device_registry()
    except Exception as e:
        result["components"]["device_registry"] = {"error": str(e)}
    try:
        from v704_permission_gate import permission_gate
        result["components"]["permissions"] = permission_gate()
    except Exception as e:
        result["components"]["permissions"] = {"error": str(e)}
    try:
        from v708_multimodal_router import multimodal_router
        result["components"]["router"] = multimodal_router("unknown")
    except Exception as e:
        result["components"]["router"] = {"error": str(e)}
    try:
        from v709_sensory_config import sensory_config
        result["components"]["config"] = sensory_config()
    except Exception as e:
        result["components"]["config"] = {"error": str(e)}
    result["status"] = "ok"
    return result


def main():
    print(f"Nova v710_sensory_body_manager")
    r = sensory_body_manager()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
