"""v819_download_packaging_manifest — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v819_download_packaging_manifest import download_packaging_manifest
    r = download_packaging_manifest()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v819_download_packaging_manifest")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v819_download_packaging_manifest: " + str(e))
    raise SystemExit(1)
