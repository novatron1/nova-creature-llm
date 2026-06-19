"""v861_autonomous_code_task_loop — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v861_autonomous_code_task_loop import autonomous_code_task_loop
    r = autonomous_code_task_loop()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v861_autonomous_code_task_loop")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v861_autonomous_code_task_loop: " + str(e))
    raise SystemExit(1)
