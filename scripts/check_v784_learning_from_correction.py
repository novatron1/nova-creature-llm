"""v784_learning_from_correction — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v784_learning_from_correction import learning_from_correction
    r = learning_from_correction()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v784_learning_from_correction")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v784_learning_from_correction: " + str(e))
    raise SystemExit(1)
