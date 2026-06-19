"""v786_rapid_absorption_test — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v786_rapid_absorption_test import rapid_absorption_test
    r = rapid_absorption_test()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v786_rapid_absorption_test")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v786_rapid_absorption_test: " + str(e))
    raise SystemExit(1)
