"""736 — Check Sensory Memory Store"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v736_sensory_memory_store import sensory_memory_store
    r = sensory_memory_store()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v736_sensory_memory_store")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v736_sensory_memory_store: " + str(e))
    raise SystemExit(1)
