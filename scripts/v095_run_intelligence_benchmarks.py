#!/usr/bin/env python3
"""v095 — Run all intelligence benchmarks."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v095_intelligence_benchmark_suite import run_critical_tests

def main():
    print("Nova v095 -- Intelligence Benchmarks\n")
    r = run_critical_tests()
    print(f"Tests: {r['passed']}/{r['total_tests']} ({r['percentage']}%)")
    for res in r["results"]:
        status = "PASS" if res["passed"] else "FAIL"
        print(f"  [{status}] {res['id']}")
    print(f"\nAll critical pass: {r['all_critical_pass']}")
    print(f"Promote ready: {r['promote_ready']}")
    (ROOT/"reports"/"v095_intelligence_benchmark_status.json").write_text(json.dumps(r, indent=2))
    print(f"\nReport: reports/v095_intelligence_benchmark_status.json")
    return 0 if r['all_critical_pass'] else 1

if __name__ == "__main__":
    raise SystemExit(main())
