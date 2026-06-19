"""747 — Check Sensory Body Dashboard"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v747_sensory_body_dashboard import sensory_body_dashboard
    r = sensory_body_dashboard()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v747_sensory_body_dashboard")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v747_sensory_body_dashboard: " + str(e))
    raise SystemExit(1)
