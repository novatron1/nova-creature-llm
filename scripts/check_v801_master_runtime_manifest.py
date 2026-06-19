"""v801_master_runtime_manifest — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v801_master_runtime_manifest import master_runtime_manifest
    r = master_runtime_manifest()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v801_master_runtime_manifest")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v801_master_runtime_manifest: " + str(e))
    raise SystemExit(1)
