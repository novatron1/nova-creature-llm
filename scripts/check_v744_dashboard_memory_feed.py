"""744 — Check Dashboard Memory Feed"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v744_dashboard_memory_feed import dashboard_memory_feed
    r = dashboard_memory_feed()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v744_dashboard_memory_feed")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v744_dashboard_memory_feed: " + str(e))
    raise SystemExit(1)
