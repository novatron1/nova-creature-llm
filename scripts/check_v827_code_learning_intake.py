"""v827_code_learning_intake — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v827_code_learning_intake import code_learning_intake
    r = code_learning_intake()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v827_code_learning_intake")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v827_code_learning_intake: " + str(e))
    raise SystemExit(1)
