"""v888_regression_trap_drills — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v888_regression_trap_drills import regression_trap_drills
    r = regression_trap_drills()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v888_regression_trap_drills")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v888_regression_trap_drills: " + str(e))
    raise SystemExit(1)
