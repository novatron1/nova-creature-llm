"""v916_training_from_codebase — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v916_training_from_codebase import training_from_codebase
    r = training_from_codebase()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v916_training_from_codebase")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v916_training_from_codebase: " + str(e))
    raise SystemExit(1)
