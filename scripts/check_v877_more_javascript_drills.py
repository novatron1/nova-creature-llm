"""v877_more_javascript_drills — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v877_more_javascript_drills import more_javascript_drills
    r = more_javascript_drills()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v877_more_javascript_drills")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v877_more_javascript_drills: " + str(e))
    raise SystemExit(1)
