"""v802_unified_event_bus — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v802_unified_event_bus import unified_event_bus
    r = unified_event_bus()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v802_unified_event_bus")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v802_unified_event_bus: " + str(e))
    raise SystemExit(1)
