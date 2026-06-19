"""740 — Check Sensory Permission Manager"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v740_sensory_permission_manager import sensory_permission_manager
    r = sensory_permission_manager()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v740_sensory_permission_manager")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v740_sensory_permission_manager: " + str(e))
    raise SystemExit(1)
