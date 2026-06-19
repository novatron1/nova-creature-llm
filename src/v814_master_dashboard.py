"""v814_master_dashboard — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def master_dashboard():
    """Master dashboard showing all system statuses."""
    now = datetime.now().isoformat()
    sections = {}
    try:
        from v741_dashboard_sensor_status import dashboard_sensor_status
        sections["sensory"] = dashboard_sensor_status()
    except: sections["sensory"] = {"status": "unavailable"}
    try:
        from v766_people_memory_dashboard import people_memory_dashboard
        sections["people_memory"] = people_memory_dashboard()
    except: sections["people_memory"] = {"status": "unavailable"}
    try:
        from v790_education_dashboard import education_dashboard
        sections["rapid_learning"] = education_dashboard()
    except: sections["rapid_learning"] = {"status": "unavailable"}
    try:
        from v803_master_permission_bridge import master_permission_bridge
        sections["permissions"] = master_permission_bridge(action="status")
    except: sections["permissions"] = {"status": "unavailable"}
    try:
        from v808_runtime_session_manager import runtime_session_manager
        sections["sessions"] = runtime_session_manager("list")
    except: sections["sessions"] = {"status": "unavailable"}
    return {"version": "v814_master_dashboard", "created_at": now,
            "sections": sections, "status": "ok"}


def main():
    print(f"Nova v814_master_dashboard")
    r = master_dashboard()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
