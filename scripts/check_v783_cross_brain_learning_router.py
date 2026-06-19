"""v783_cross_brain_learning_router — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v783_cross_brain_learning_router import cross_brain_learning_router
    r = cross_brain_learning_router()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v783_cross_brain_learning_router")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v783_cross_brain_learning_router: " + str(e))
    raise SystemExit(1)
