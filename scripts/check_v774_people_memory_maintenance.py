"""v774_people_memory_maintenance — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v774_people_memory_maintenance import people_memory_maintenance
    r = people_memory_maintenance()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v774_people_memory_maintenance")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v774_people_memory_maintenance: " + str(e))
    raise SystemExit(1)
