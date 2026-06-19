"""v865_coding_master_benchmark — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v865_coding_master_benchmark import coding_master_benchmark
    r = coding_master_benchmark()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v865_coding_master_benchmark")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v865_coding_master_benchmark: " + str(e))
    raise SystemExit(1)
