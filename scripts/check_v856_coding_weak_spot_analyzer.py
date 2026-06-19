"""v856_coding_weak_spot_analyzer — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v856_coding_weak_spot_analyzer import coding_weak_spot_analyzer
    r = coding_weak_spot_analyzer()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v856_coding_weak_spot_analyzer")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v856_coding_weak_spot_analyzer: " + str(e))
    raise SystemExit(1)
