"""v949_final_training_lab_scorecard — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v949_final_training_lab_scorecard import final_training_lab_scorecard
    r = final_training_lab_scorecard()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v949_final_training_lab_scorecard")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v949_final_training_lab_scorecard: " + str(e))
    raise SystemExit(1)
