"""731 — Check Screen Capture Discovery"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v731_screen_capture_discovery import screen_capture_discovery
    r = screen_capture_discovery()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v731_screen_capture_discovery")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v731_screen_capture_discovery: " + str(e))
    raise SystemExit(1)
