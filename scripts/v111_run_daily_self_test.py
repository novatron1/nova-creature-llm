#!/usr/bin/env python3
"""Run daily self-test and print results."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v111_daily_self_test import run_daily_self_test

def main():
    r = run_daily_self_test()
    print(f"Nova v111 -- Daily Self-Test Report\n")
    for res in r['results']:
        status = "✅" if res['status'] == "PASS" else "❌"
        print(f"  {status} {res['test']}: {res['description']} ({res['status']})")
    print(f"\nPassed: {r['passed']}/{r['total']}")
    (ROOT / "reports" / "v111_daily_self_test_status.json").write_text(
        __import__('json').dumps(r, indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
