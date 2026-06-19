"""v887_multi_file_patch_drills — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v887_multi_file_patch_drills import multi_file_patch_drills
    r = multi_file_patch_drills()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v887_multi_file_patch_drills")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v887_multi_file_patch_drills: " + str(e))
    raise SystemExit(1)
