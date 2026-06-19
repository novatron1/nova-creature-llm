"""v813_full_loop_demo_script — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v813_full_loop_demo_script import full_loop_demo_script
    r = full_loop_demo_script()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v813_full_loop_demo_script")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v813_full_loop_demo_script: " + str(e))
    raise SystemExit(1)
