"""v919_training_from_failed_patches — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v919_training_from_failed_patches import training_from_failed_patches
    r = training_from_failed_patches()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v919_training_from_failed_patches")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v919_training_from_failed_patches: " + str(e))
    raise SystemExit(1)
