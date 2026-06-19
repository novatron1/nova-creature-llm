"""v794_learning_streak_tracker — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v794_learning_streak_tracker import learning_streak_tracker
    r = learning_streak_tracker()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v794_learning_streak_tracker")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v794_learning_streak_tracker: " + str(e))
    raise SystemExit(1)
