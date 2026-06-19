"""v756_known_unknown_person_router — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v756_known_unknown_person_router import known_unknown_person_router
    r = known_unknown_person_router()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v756_known_unknown_person_router")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v756_known_unknown_person_router: " + str(e))
    raise SystemExit(1)
