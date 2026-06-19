"""v954_role_separate_test_round_1 — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v954_role_separate_test_round_1 import role_separate_test_round_1
    r = role_separate_test_round_1()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v954_role_separate_test_round_1")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v954_role_separate_test_round_1: " + str(e))
    raise SystemExit(1)
