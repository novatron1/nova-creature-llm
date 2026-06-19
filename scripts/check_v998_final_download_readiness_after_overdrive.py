"""v998_final_download_readiness_after_overdrive — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v998_final_download_readiness_after_overdrive import final_download_readiness_after_overdrive
    r = final_download_readiness_after_overdrive()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v998_final_download_readiness_after_overdrive")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v998_final_download_readiness_after_overdrive: " + str(e))
    raise SystemExit(1)
