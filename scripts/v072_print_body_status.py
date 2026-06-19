#!/usr/bin/env python3
"""Print body sensor status."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v072_body_sensor_registry import save_registry

STATUS_ICONS = {
    "active": "[ACTIVE]",
    "missing": "[MISSING]",
    "not_installed": "[MISSING]",
    "not_connected": "[OFFLINE]",
    "planned": "[PLANNED]",
    "inactive": "[INACTIVE]",
}

def main():
    r = save_registry()
    print("Nova v072 -- Body Sensor Status\n")
    print(f"real_hardware_enabled: {r['real_hardware_enabled']}\n")
    for name, info in r["sensors"].items():
        icon = STATUS_ICONS.get(info["status"], "[?]")
        print(f"  {icon} {name}: {info['status']}")
        if info.get("missing_reason"):
            print(f"     {info['missing_reason']}")
    print()
    print(f"Active: {r['sensors_connected']}, Missing: {r['sensors_missing']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
