"""v937_export_best_training_set — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v937_export_best_training_set import export_best_training_set
    r = export_best_training_set()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v937_export_best_training_set")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v937_export_best_training_set: " + str(e))
    raise SystemExit(1)
