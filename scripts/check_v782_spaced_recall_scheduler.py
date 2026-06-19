"""v782_spaced_recall_scheduler — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v782_spaced_recall_scheduler import spaced_recall_scheduler
    r = spaced_recall_scheduler()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v782_spaced_recall_scheduler")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v782_spaced_recall_scheduler: " + str(e))
    raise SystemExit(1)
