"""v989_mastery_threshold_update — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v989_mastery_threshold_update import mastery_threshold_update
    r = mastery_threshold_update()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v989_mastery_threshold_update")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v989_mastery_threshold_update: " + str(e))
    raise SystemExit(1)
