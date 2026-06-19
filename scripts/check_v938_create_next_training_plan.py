"""v938_create_next_training_plan — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v938_create_next_training_plan import create_next_training_plan
    r = create_next_training_plan()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v938_create_next_training_plan")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v938_create_next_training_plan: " + str(e))
    raise SystemExit(1)
