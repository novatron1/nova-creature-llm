"""v808_runtime_session_manager — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v808_runtime_session_manager import runtime_session_manager
    r = runtime_session_manager()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v808_runtime_session_manager")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v808_runtime_session_manager: " + str(e))
    raise SystemExit(1)
