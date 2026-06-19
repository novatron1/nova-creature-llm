"""v992_overdrive_retention_report — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v992_overdrive_retention_report import overdrive_retention_report
    r = overdrive_retention_report()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v992_overdrive_retention_report")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v992_overdrive_retention_report: " + str(e))
    raise SystemExit(1)
