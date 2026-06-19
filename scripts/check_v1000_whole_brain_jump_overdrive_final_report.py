"""v1000_whole_brain_jump_overdrive_final_report — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v1000_whole_brain_jump_overdrive_final_report import whole_brain_jump_overdrive_final_report
    r = whole_brain_jump_overdrive_final_report()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v1000_whole_brain_jump_overdrive_final_report")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v1000_whole_brain_jump_overdrive_final_report: " + str(e))
    raise SystemExit(1)
