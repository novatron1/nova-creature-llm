"""710 — Check Sensory Body Manager"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v710_sensory_body_manager import sensory_body_manager
    r = sensory_body_manager()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v710_sensory_body_manager")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v710_sensory_body_manager: " + str(e))
    raise SystemExit(1)
