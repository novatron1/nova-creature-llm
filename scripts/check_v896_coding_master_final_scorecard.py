"""v896_coding_master_final_scorecard — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v896_coding_master_final_scorecard import coding_master_final_scorecard
    r = coding_master_final_scorecard()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v896_coding_master_final_scorecard")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v896_coding_master_final_scorecard: " + str(e))
    raise SystemExit(1)
