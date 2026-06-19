"""745 — Check Dashboard Brain Route Display"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v745_dashboard_brain_route_display import dashboard_brain_route_display
    r = dashboard_brain_route_display()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v745_dashboard_brain_route_display")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v745_dashboard_brain_route_display: " + str(e))
    raise SystemExit(1)
