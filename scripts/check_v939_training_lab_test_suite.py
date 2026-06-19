"""v939_training_lab_test_suite — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v939_training_lab_test_suite import training_lab_test_suite
    r = training_lab_test_suite()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v939_training_lab_test_suite")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v939_training_lab_test_suite: " + str(e))
    raise SystemExit(1)
