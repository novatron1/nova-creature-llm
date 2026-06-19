"""v872_integrate_with_brain_router — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v872_integrate_with_brain_router import integrate_with_brain_router
    r = integrate_with_brain_router()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v872_integrate_with_brain_router")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v872_integrate_with_brain_router: " + str(e))
    raise SystemExit(1)
