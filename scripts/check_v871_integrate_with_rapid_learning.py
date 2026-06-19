"""v871_integrate_with_rapid_learning — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v871_integrate_with_rapid_learning import integrate_with_rapid_learning
    r = integrate_with_rapid_learning()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v871_integrate_with_rapid_learning")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v871_integrate_with_rapid_learning: " + str(e))
    raise SystemExit(1)
