"""v910_training_comparison_reporter — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v910_training_comparison_reporter import training_comparison_reporter
    r = training_comparison_reporter()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v910_training_comparison_reporter")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v910_training_comparison_reporter: " + str(e))
    raise SystemExit(1)
