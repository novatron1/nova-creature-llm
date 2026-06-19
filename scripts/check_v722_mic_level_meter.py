"""722 — Check Mic Level Meter"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v722_mic_level_meter import mic_level_meter
    r = mic_level_meter()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v722_mic_level_meter")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v722_mic_level_meter: " + str(e))
    raise SystemExit(1)
