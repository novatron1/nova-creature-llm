"""v996_overdrive_training_scorecard — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v996_overdrive_training_scorecard import overdrive_training_scorecard
    r = overdrive_training_scorecard()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v996_overdrive_training_scorecard")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v996_overdrive_training_scorecard: " + str(e))
    raise SystemExit(1)
