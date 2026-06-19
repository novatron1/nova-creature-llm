"""v914_failed_training_quarantine — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v914_failed_training_quarantine import failed_training_quarantine
    r = failed_training_quarantine()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v914_failed_training_quarantine")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v914_failed_training_quarantine: " + str(e))
    raise SystemExit(1)
