"""v917_training_from_error_logs — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v917_training_from_error_logs import training_from_error_logs
    r = training_from_error_logs()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v917_training_from_error_logs")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v917_training_from_error_logs: " + str(e))
    raise SystemExit(1)
