"""v811_conflict_and_truth_guard — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v811_conflict_and_truth_guard import conflict_and_truth_guard
    r = conflict_and_truth_guard()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v811_conflict_and_truth_guard")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v811_conflict_and_truth_guard: " + str(e))
    raise SystemExit(1)
