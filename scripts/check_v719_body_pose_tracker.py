"""719 — Check Body Pose Tracker"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v719_body_pose_tracker import body_pose_tracker
    r = body_pose_tracker()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v719_body_pose_tracker")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v719_body_pose_tracker: " + str(e))
    raise SystemExit(1)
