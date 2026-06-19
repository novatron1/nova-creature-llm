"""v950_whole_brain_training_final_report — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v950_whole_brain_training_final_report import whole_brain_training_final_report
    r = whole_brain_training_final_report()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v950_whole_brain_training_final_report")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v950_whole_brain_training_final_report: " + str(e))
    raise SystemExit(1)
