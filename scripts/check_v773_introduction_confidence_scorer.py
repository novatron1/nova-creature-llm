"""v773_introduction_confidence_scorer — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v773_introduction_confidence_scorer import introduction_confidence_scorer
    r = introduction_confidence_scorer()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v773_introduction_confidence_scorer")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v773_introduction_confidence_scorer: " + str(e))
    raise SystemExit(1)
