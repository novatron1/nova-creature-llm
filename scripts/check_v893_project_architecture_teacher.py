"""v893_project_architecture_teacher — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v893_project_architecture_teacher import project_architecture_teacher
    r = project_architecture_teacher()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v893_project_architecture_teacher")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v893_project_architecture_teacher: " + str(e))
    raise SystemExit(1)
