"""v831_stack_trace_solver — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v831_stack_trace_solver import stack_trace_solver
    r = stack_trace_solver()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v831_stack_trace_solver")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v831_stack_trace_solver: " + str(e))
    raise SystemExit(1)
