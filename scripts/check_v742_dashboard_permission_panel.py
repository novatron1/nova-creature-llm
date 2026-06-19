"""742 — Check Dashboard Permission Panel"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v742_dashboard_permission_panel import dashboard_permission_panel
    r = dashboard_permission_panel()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v742_dashboard_permission_panel")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v742_dashboard_permission_panel: " + str(e))
    raise SystemExit(1)
