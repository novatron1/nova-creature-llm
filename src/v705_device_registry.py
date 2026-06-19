"""705 — Sensory Body Layer: Device Registry"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def device_registry():
    """Central device registry combining discovery, selection, and permissions."""
    result = {"version": "v705_device_registry", "created_at": datetime.now().isoformat(),
              "devices": {}, "selections": {}, "permissions": {}, "status": "ok"}
    try:
        from v701_device_scanner import device_scanner
        result["devices"] = device_scanner()
    except Exception as e:
        result["devices"] = {"error": str(e)}
    try:
        from v702_device_selector import device_selector
        result["selections"] = device_selector(result.get("devices"))
    except Exception as e:
        result["selections"] = {"error": str(e)}
    try:
        from v704_permission_gate import permission_gate
        result["permissions"] = permission_gate()
    except Exception as e:
        result["permissions"] = {"error": str(e)}
    result["status"] = "ok"
    return result


def main():
    print(f"Nova v705_device_registry")
    r = device_registry()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
