"""741 — Check Dashboard Sensor Status"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v741_dashboard_sensor_status import dashboard_sensor_status
    r = dashboard_sensor_status()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v741_dashboard_sensor_status")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v741_dashboard_sensor_status: " + str(e))
    raise SystemExit(1)
