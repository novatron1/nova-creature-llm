"""v849_coding_memory_lock — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v849_coding_memory_lock import coding_memory_lock
    r = coding_memory_lock()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v849_coding_memory_lock")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v849_coding_memory_lock: " + str(e))
    raise SystemExit(1)
