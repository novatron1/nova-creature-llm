"""v765_people_memory_tests — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v765_people_memory_tests import people_memory_tests
    r = people_memory_tests()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v765_people_memory_tests")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v765_people_memory_tests: " + str(e))
    raise SystemExit(1)
