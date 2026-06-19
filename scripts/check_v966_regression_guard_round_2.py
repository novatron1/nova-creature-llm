"""v966_regression_guard_round_2 — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v966_regression_guard_round_2 import regression_guard_round_2
    r = regression_guard_round_2()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v966_regression_guard_round_2")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v966_regression_guard_round_2: " + str(e))
    raise SystemExit(1)
