#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v449_benchmark_regression import simulate_benchmark_regression
import json
def main():
    r = simulate_benchmark_regression()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v449_gold_benchmark_regression_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
