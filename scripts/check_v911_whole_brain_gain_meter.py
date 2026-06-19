"""v911_whole_brain_gain_meter — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v911_whole_brain_gain_meter import whole_brain_gain_meter
    r = whole_brain_gain_meter()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v911_whole_brain_gain_meter")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v911_whole_brain_gain_meter: " + str(e))
    raise SystemExit(1)
