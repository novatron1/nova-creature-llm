"""v984_training_method_confirmation — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v984_training_method_confirmation import training_method_confirmation
    r = training_method_confirmation()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v984_training_method_confirmation")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v984_training_method_confirmation: " + str(e))
    raise SystemExit(1)
