"""v915_training_from_user_teaching — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v915_training_from_user_teaching import training_from_user_teaching
    r = training_from_user_teaching()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v915_training_from_user_teaching")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v915_training_from_user_teaching: " + str(e))
    raise SystemExit(1)
