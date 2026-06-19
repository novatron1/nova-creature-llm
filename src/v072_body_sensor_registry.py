"""v072 — Body Sensor Registry."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SENSORS = {
    "camera": {"exists": False, "active": False, "required_for_real_movement": True, "status": "not_connected",
               "missing_reason": "No camera hardware connected", "safe_to_use": False},
    "microphone": {"exists": False, "active": False, "required_for_real_movement": False, "status": "not_connected",
                   "missing_reason": "No microphone hardware connected", "safe_to_use": False},
    "speaker": {"exists": False, "active": False, "required_for_real_movement": False, "status": "planned",
                "missing_reason": "Speaker output not configured", "safe_to_use": False},
    "movement_base": {"exists": False, "active": False, "required_for_real_movement": True, "status": "inactive",
                      "missing_reason": "No movement hardware", "safe_to_use": False},
    "robotic_arm": {"exists": False, "active": False, "required_for_real_movement": True, "status": "inactive",
                    "missing_reason": "No robotic arm hardware", "safe_to_use": False},
    "lidar_or_distance_sensor": {"exists": False, "active": False, "required_for_real_movement": True, "status": "not_installed",
                                 "missing_reason": "Requires physical LIDAR sensor", "safe_to_use": False},
    "imu_balance_sensor": {"exists": False, "active": False, "required_for_real_movement": True, "status": "not_installed",
                           "missing_reason": "Requires IMU hardware", "safe_to_use": False},
    "battery_monitor": {"exists": False, "active": False, "required_for_real_movement": True, "status": "not_installed",
                        "missing_reason": "Requires power management hardware", "safe_to_use": False},
    "emergency_stop": {"exists": False, "active": False, "required_for_real_movement": True, "status": "missing",
                       "missing_reason": "Emergency stop not installed", "safe_to_use": False},
    "collision_sensor": {"exists": False, "active": False, "required_for_real_movement": True, "status": "missing",
                         "missing_reason": "Collision sensor not installed", "safe_to_use": False},
    "human_distance_sensor": {"exists": False, "active": False, "required_for_real_movement": True, "status": "missing",
                              "missing_reason": "Human distance sensor not installed", "safe_to_use": False},
    "hardware_config": {"exists": False, "active": False, "required_for_real_movement": True, "status": "missing",
                        "missing_reason": "Real hardware configuration not present", "safe_to_use": False},
    "simulation_world": {"exists": True, "active": True, "required_for_real_movement": True, "status": "active",
                         "missing_reason": "", "safe_to_use": True},
}

def build_registry() -> dict[str, Any]:
    registry = {}
    for name, info in DEFAULT_SENSORS.items():
        entry = {**info, "last_checked": datetime.now().isoformat()}
        registry[name] = entry
    return {
        "version": "v072_body_sensor_registry",
        "created_at": datetime.now().isoformat(),
        "sensors": registry,
        "real_hardware_enabled": False,
        "sensors_connected": sum(1 for s in registry.values() if s["active"]),
        "sensors_missing": sum(1 for s in registry.values() if s["status"] in ("missing", "not_installed", "not_connected")),
    }

def save_registry():
    r = build_registry()
    path = ROOT / "data" / "body" / "body_sensor_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(r, indent=2))
    return r

def main():
    print("Nova v072 -- Body Sensor Registry\n")
    r = save_registry()
    print(f"Sensors: {len(r['sensors'])}")
    print(f"Active: {r['sensors_connected']} / Missing: {r['sensors_missing']}")
    print(f"real_hardware_enabled: {r['real_hardware_enabled']}")
    for name, info in r['sensors'].items():
        if info['active']:
            print(f"  ACTIVE: {name}")
    for name, info in r['sensors'].items():
        if info['status'] in ('missing','not_installed','not_connected'):
            print(f"  MISSING: {name} - {info['missing_reason']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
