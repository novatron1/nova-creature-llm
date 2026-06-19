"""v922_long_context_project_memory_test — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v922_long_context_project_memory_test import long_context_project_memory_test
    r = long_context_project_memory_test()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v922_long_context_project_memory_test")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v922_long_context_project_memory_test: " + str(e))
    raise SystemExit(1)
