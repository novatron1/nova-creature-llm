"""715 — Check Head Pose Estimator"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v715_head_pose_estimator import head_pose_estimator
    r = head_pose_estimator()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v715_head_pose_estimator")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v715_head_pose_estimator: " + str(e))
    raise SystemExit(1)
