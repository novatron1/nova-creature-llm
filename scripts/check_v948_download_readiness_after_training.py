"""v948_download_readiness_after_training — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v948_download_readiness_after_training import download_readiness_after_training
    r = download_readiness_after_training()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v948_download_readiness_after_training")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v948_download_readiness_after_training: " + str(e))
    raise SystemExit(1)
