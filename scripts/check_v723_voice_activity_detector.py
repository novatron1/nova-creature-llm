"""723 — Check Voice Activity Detector"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v723_voice_activity_detector import voice_activity_detector
    r = voice_activity_detector()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v723_voice_activity_detector")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v723_voice_activity_detector: " + str(e))
    raise SystemExit(1)
