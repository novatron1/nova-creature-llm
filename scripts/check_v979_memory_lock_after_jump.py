"""v979_memory_lock_after_jump — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v979_memory_lock_after_jump import memory_lock_after_jump
    r = memory_lock_after_jump()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v979_memory_lock_after_jump")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v979_memory_lock_after_jump: " + str(e))
    raise SystemExit(1)
