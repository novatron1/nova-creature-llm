"""v903_training_dataset_builder — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v903_training_dataset_builder import training_dataset_builder
    r = training_dataset_builder()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v903_training_dataset_builder")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v903_training_dataset_builder: " + str(e))
    raise SystemExit(1)
