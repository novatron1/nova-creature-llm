"""v803_master_permission_bridge — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v803_master_permission_bridge import master_permission_bridge
    r = master_permission_bridge()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v803_master_permission_bridge")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v803_master_permission_bridge: " + str(e))
    raise SystemExit(1)
