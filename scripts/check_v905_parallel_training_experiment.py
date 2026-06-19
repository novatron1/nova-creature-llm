"""v905_parallel_training_experiment — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v905_parallel_training_experiment import parallel_training_experiment
    r = parallel_training_experiment()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v905_parallel_training_experiment")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v905_parallel_training_experiment: " + str(e))
    raise SystemExit(1)
