"""v920_brain_role_specialization_report — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v920_brain_role_specialization_report import brain_role_specialization_report
    r = brain_role_specialization_report()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v920_brain_role_specialization_report")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v920_brain_role_specialization_report: " + str(e))
    raise SystemExit(1)
