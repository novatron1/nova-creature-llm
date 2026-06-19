#!/usr/bin/env python3
"""Print benchmark dashboard."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v075_benchmark_dashboard import run_all_benchmarks

def main():
    r = run_all_benchmarks()
    print("Nova v075 -- Benchmark Dashboard\n")
    print(f"Overall: {r['total_passed']}/{r['total_tests']} ({r['overall_percentage']}%)\n")
    for res in r['results']:
        icon = "\u2705" if res['passed'] else "\u274c"
        print(f"  {icon} {res['name']}: {res['status']} ({res['percentage']}%)")
        if res['blockers']:
            for b in res['blockers']:
                print(f"     BLOCKER: {b}")
    print(f"\nAll passed: {r['all_passed']}")
    (ROOT/"reports"/"v075_benchmark_dashboard_status.json").write_text(json.dumps(r, indent=2))
    print(f"Report: reports/v075_benchmark_dashboard_status.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
