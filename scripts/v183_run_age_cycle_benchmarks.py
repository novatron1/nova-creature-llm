#!/usr/bin/env python3
"""Run age-cycle benchmarks."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v183_age_cycle_benchmark_pack import run_age_cycle_benchmarks
def main():
    r = run_age_cycle_benchmarks()
    print(f"\nAge-Cycle Benchmark Results:")
    for res in r["results"]:
        status = "PASS" if res["passed"] else "FAIL"
        print(f"  [{status}] {res['category']}: {res['tests']} tests")
    print(f"\nOverall: {r['passed']}/{r['total']}")
    (ROOT/"reports"/"v183_age_cycle_benchmark_status.json").write_text(json.dumps(r, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
