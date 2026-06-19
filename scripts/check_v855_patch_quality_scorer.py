"""v855_patch_quality_scorer — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v855_patch_quality_scorer import patch_quality_scorer
    r = patch_quality_scorer()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v855_patch_quality_scorer")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v855_patch_quality_scorer: " + str(e))
    raise SystemExit(1)
