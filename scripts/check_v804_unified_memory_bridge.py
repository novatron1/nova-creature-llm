"""v804_unified_memory_bridge — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v804_unified_memory_bridge import unified_memory_bridge
    r = unified_memory_bridge()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v804_unified_memory_bridge")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v804_unified_memory_bridge: " + str(e))
    raise SystemExit(1)
