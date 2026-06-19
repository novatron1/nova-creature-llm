"""v836_self_debug_loop — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v836_self_debug_loop import self_debug_loop
    r = self_debug_loop()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v836_self_debug_loop")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v836_self_debug_loop: " + str(e))
    raise SystemExit(1)
