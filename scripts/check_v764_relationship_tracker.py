"""v764_relationship_tracker — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v764_relationship_tracker import relationship_tracker
    r = relationship_tracker()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v764_relationship_tracker")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v764_relationship_tracker: " + str(e))
    raise SystemExit(1)
