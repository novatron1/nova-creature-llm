"""v852_frontend_repair_simulator — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v852_frontend_repair_simulator import frontend_repair_simulator
    r = frontend_repair_simulator()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v852_frontend_repair_simulator")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v852_frontend_repair_simulator: " + str(e))
    raise SystemExit(1)
