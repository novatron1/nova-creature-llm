"""v847_error_repair_dataset — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v847_error_repair_dataset import error_repair_dataset
    r = error_repair_dataset()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v847_error_repair_dataset")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v847_error_repair_dataset: " + str(e))
    raise SystemExit(1)
