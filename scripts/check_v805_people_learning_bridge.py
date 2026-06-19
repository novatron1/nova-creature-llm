"""v805_people_learning_bridge — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v805_people_learning_bridge import people_learning_bridge
    r = people_learning_bridge()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v805_people_learning_bridge")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v805_people_learning_bridge: " + str(e))
    raise SystemExit(1)
