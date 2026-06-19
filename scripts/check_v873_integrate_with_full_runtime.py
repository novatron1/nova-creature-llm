"""v873_integrate_with_full_runtime — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v873_integrate_with_full_runtime import integrate_with_full_runtime
    r = integrate_with_full_runtime()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v873_integrate_with_full_runtime")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v873_integrate_with_full_runtime: " + str(e))
    raise SystemExit(1)
