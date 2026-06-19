"""v981_best_jump_training_export — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v981_best_jump_training_export import best_jump_training_export
    r = best_jump_training_export()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v981_best_jump_training_export")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v981_best_jump_training_export: " + str(e))
    raise SystemExit(1)
