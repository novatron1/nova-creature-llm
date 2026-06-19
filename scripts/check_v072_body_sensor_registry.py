#!/usr/bin/env python3
"""Check v072 body sensor registry."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v072_body_sensor_registry import build_registry, DEFAULT_SENSORS
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  \u2705 {msg}")
    else: E.append(f"  \u274c {msg}")
def main():
    print("Nova v072 -- Body Sensor Registry Checker\n")
    c(Path(ROOT/"src"/"v072_body_sensor_registry.py").exists(), "src exists")
    r = build_registry()
    c(len(r["sensors"]) == 13, f"13 sensors ({len(r['sensors'])})")
    c(r["real_hardware_enabled"] == False, "hardware disabled")
    c("simulation_world" in r["sensors"], "sim world present")
    c(r["sensors"]["simulation_world"]["active"], "sim world active")
    c(r["sensors"]["emergency_stop"]["active"] == False, "emergency stop inactive")
    c(r["sensors"]["hardware_config"]["active"] == False, "hardware config missing")
    c(r["sensors_connected"] >= 1, "at least sim world active")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
