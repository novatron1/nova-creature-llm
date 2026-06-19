#!/usr/bin/env python3
"""Print intelligence gain report."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v179_intelligence_gain_report import generate_gain_report
def main():
    r = generate_gain_report()
    print(f"Nova Intelligence Gain Report\n")
    print(f"Before: {r['benchmark_before']}")
    print(f"After:  {r['benchmark_after']}")
    print(f"Gains:  {r['gains_by_category']}")
    print(f"Regressions: {r['regressions']}")
    print(f"Overall: {r['overall_gain']}")
    return 0
if __name__ == "__main__": raise SystemExit(main())
