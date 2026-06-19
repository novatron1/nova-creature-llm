"""747 — Sensory Body Layer: Sensory Body Dashboard"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def sensory_body_dashboard():
    """Full sensory body dashboard composer."""
    result = {"version": "v747_sensory_body_dashboard", "created_at": datetime.now().isoformat(), "status": "ok"}
    try:
        from v746_dashboard_control_panel import dashboard_control_panel
        result["dashboard"] = dashboard_control_panel()
    except Exception as e:
        result["dashboard"] = {"error": str(e)}
    result["summary"] = {
        "sensors_online": 0,
        "permissions_granted": False,
        "signals_detected": False,
        "memory_available": False,
        "brain_routes_configured": True,
    }
    if "dashboard" in result and isinstance(result["dashboard"], dict):
        sensors = result["dashboard"].get("sections", {}).get("sensor_status", {})
        perms = result["dashboard"].get("sections", {}).get("permissions", {})
        signals = result["dashboard"].get("sections", {}).get("signals", {})
        mem = result["dashboard"].get("sections", {}).get("memory_feed", {})
        result["summary"]["sensors_online"] = sum(1 for s in (sensors.get("sensors", {}) if isinstance(sensors, dict) else {}).values() if s.get("available"))
        result["summary"]["permissions_granted"] = True
        result["summary"]["signals_detected"] = True
        result["summary"]["memory_available"] = isinstance(mem, dict) and mem.get("count", 0) > 0
    return result


def main():
    print(f"Nova v747_sensory_body_dashboard")
    r = sensory_body_dashboard()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
