"""742 — Sensory Body Layer: Dashboard Permission Panel"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def dashboard_permission_panel():
    """Display permission status for all sensory inputs."""
    result = {"version": "v742_dashboard_permission_panel", "created_at": datetime.now().isoformat(), "status": "ok"}
    try:
        from v740_sensory_permission_manager import sensory_permission_manager
        result["permissions"] = sensory_permission_manager()
    except Exception as e:
        from v704_permission_gate import permission_gate
        result["permissions"] = permission_gate()
    result["all_required_granted"] = all(p.get("granted", False) for p in result.get("permissions", {}).get("permissions", {}).values()) if isinstance(result.get("permissions"), dict) else False
    return result


def main():
    print(f"Nova v742_dashboard_permission_panel")
    r = dashboard_permission_panel()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
