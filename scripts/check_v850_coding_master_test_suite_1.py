"""v850_coding_master_test_suite_1 — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v850_coding_master_test_suite_1 import coding_master_test_suite_1
    r = coding_master_test_suite_1()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v850_coding_master_test_suite_1")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v850_coding_master_test_suite_1: " + str(e))
    raise SystemExit(1)
