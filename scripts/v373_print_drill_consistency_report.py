#!/usr/bin/env python3
"""Print Drill Consistency Report."""
from __future__ import annotations
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v373_drill_consistency_report import generate_consistency_report
def main():
    r = generate_consistency_report()
    print(f"\n{'='*60}")
    print(f"Nova v373 - Drill Consistency Report")
    print(f"{'='*60}")
    for k,v in r.items():
        print(f"  {k}: {v}")
    print(f"{'='*60}\n")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
