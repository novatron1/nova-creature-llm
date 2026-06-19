"""v772_people_memory_sync — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v772_people_memory_sync import people_memory_sync
    r = people_memory_sync()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v772_people_memory_sync")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v772_people_memory_sync: " + str(e))
    raise SystemExit(1)
