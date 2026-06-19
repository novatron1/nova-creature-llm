"""v762_profile_merge_detector — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v762_profile_merge_detector import profile_merge_detector
    r = profile_merge_detector()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v762_profile_merge_detector")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v762_profile_merge_detector: " + str(e))
    raise SystemExit(1)
