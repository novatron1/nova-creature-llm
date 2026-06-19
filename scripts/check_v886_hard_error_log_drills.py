"""v886_hard_error_log_drills — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v886_hard_error_log_drills import hard_error_log_drills
    r = hard_error_log_drills()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v886_hard_error_log_drills")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v886_hard_error_log_drills: " + str(e))
    raise SystemExit(1)
