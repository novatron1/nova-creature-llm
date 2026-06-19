"""v902_baseline_benchmark_runner — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v902_baseline_benchmark_runner import baseline_benchmark_runner
    r = baseline_benchmark_runner()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v902_baseline_benchmark_runner")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v902_baseline_benchmark_runner: " + str(e))
    raise SystemExit(1)
