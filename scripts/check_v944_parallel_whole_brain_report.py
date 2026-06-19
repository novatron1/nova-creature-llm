"""v944_parallel_whole_brain_report — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v944_parallel_whole_brain_report import parallel_whole_brain_report
    r = parallel_whole_brain_report()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v944_parallel_whole_brain_report")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v944_parallel_whole_brain_report: " + str(e))
    raise SystemExit(1)
