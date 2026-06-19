"""v869_full_feature_add_drill — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v869_full_feature_add_drill import full_feature_add_drill
    r = full_feature_add_drill()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v869_full_feature_add_drill")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v869_full_feature_add_drill: " + str(e))
    raise SystemExit(1)
