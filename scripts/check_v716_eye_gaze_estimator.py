"""716 — Check Eye Gaze Estimator"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v716_eye_gaze_estimator import eye_gaze_estimator
    r = eye_gaze_estimator()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v716_eye_gaze_estimator")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v716_eye_gaze_estimator: " + str(e))
    raise SystemExit(1)
