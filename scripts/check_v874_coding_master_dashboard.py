"""v874_coding_master_dashboard — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v874_coding_master_dashboard import coding_master_dashboard
    r = coding_master_dashboard()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v874_coding_master_dashboard")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v874_coding_master_dashboard: " + str(e))
    raise SystemExit(1)
