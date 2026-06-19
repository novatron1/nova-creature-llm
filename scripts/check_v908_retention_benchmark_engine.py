"""v908_retention_benchmark_engine — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v908_retention_benchmark_engine import retention_benchmark_engine
    r = retention_benchmark_engine()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v908_retention_benchmark_engine")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v908_retention_benchmark_engine: " + str(e))
    raise SystemExit(1)
