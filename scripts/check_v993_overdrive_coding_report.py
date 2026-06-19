"""v993_overdrive_coding_report — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v993_overdrive_coding_report import overdrive_coding_report
    r = overdrive_coding_report()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v993_overdrive_coding_report")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v993_overdrive_coding_report: " + str(e))
    raise SystemExit(1)
