"""743 — Check Dashboard Signal Display"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v743_dashboard_signal_display import dashboard_signal_display
    r = dashboard_signal_display()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v743_dashboard_signal_display")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v743_dashboard_signal_display: " + str(e))
    raise SystemExit(1)
