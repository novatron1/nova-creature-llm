"""746 — Sensory Body Layer: Dashboard Control Panel"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def dashboard_control_panel():
    """Main sensory control panel combining all dashboard sections."""
    result = {"version": "v746_dashboard_control_panel", "created_at": datetime.now().isoformat(), "sections": {}, "status": "ok"}
    try:
        from v741_dashboard_sensor_status import dashboard_sensor_status
        result["sections"]["sensor_status"] = dashboard_sensor_status()
    except Exception as e:
        result["sections"]["sensor_status"] = {"error": str(e)}
    try:
        from v742_dashboard_permission_panel import dashboard_permission_panel
        result["sections"]["permissions"] = dashboard_permission_panel()
    except Exception as e:
        result["sections"]["permissions"] = {"error": str(e)}
    try:
        from v743_dashboard_signal_display import dashboard_signal_display
        result["sections"]["signals"] = dashboard_signal_display()
    except Exception as e:
        result["sections"]["signals"] = {"error": str(e)}
    try:
        from v744_dashboard_memory_feed import dashboard_memory_feed
        result["sections"]["memory_feed"] = dashboard_memory_feed(5)
    except Exception as e:
        result["sections"]["memory_feed"] = {"error": str(e)}
    try:
        from v745_dashboard_brain_route_display import dashboard_brain_route_display
        result["sections"]["brain_routes"] = dashboard_brain_route_display()
    except Exception as e:
        result["sections"]["brain_routes"] = {"error": str(e)}
    return result


def main():
    print(f"Nova v746_dashboard_control_panel")
    r = dashboard_control_panel()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
