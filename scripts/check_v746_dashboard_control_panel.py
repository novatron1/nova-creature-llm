"""746 — Check Dashboard Control Panel"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v746_dashboard_control_panel import dashboard_control_panel
    r = dashboard_control_panel()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v746_dashboard_control_panel")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v746_dashboard_control_panel: " + str(e))
    raise SystemExit(1)
