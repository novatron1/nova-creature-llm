"""v771_auto_greeting_engine — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v771_auto_greeting_engine import auto_greeting_engine
    r = auto_greeting_engine()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v771_auto_greeting_engine")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v771_auto_greeting_engine: " + str(e))
    raise SystemExit(1)
