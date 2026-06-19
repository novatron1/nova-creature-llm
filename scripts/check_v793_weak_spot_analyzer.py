"""v793_weak_spot_analyzer — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v793_weak_spot_analyzer import weak_spot_analyzer
    r = weak_spot_analyzer()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v793_weak_spot_analyzer")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v793_weak_spot_analyzer: " + str(e))
    raise SystemExit(1)
