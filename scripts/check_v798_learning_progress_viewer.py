"""v798_learning_progress_viewer — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v798_learning_progress_viewer import learning_progress_viewer
    r = learning_progress_viewer()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v798_learning_progress_viewer")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v798_learning_progress_viewer: " + str(e))
    raise SystemExit(1)
