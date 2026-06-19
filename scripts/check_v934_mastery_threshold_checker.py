"""v934_mastery_threshold_checker — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v934_mastery_threshold_checker import mastery_threshold_checker
    r = mastery_threshold_checker()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v934_mastery_threshold_checker")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v934_mastery_threshold_checker: " + str(e))
    raise SystemExit(1)
