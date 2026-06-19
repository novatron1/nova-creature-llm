#!/usr/bin/env python3
"""Print Intelligence Supercharger Report."""
from __future__ import annotations
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v390_intelligence_supercharger_report import generate_supercharger_report
def main():
    r = generate_supercharger_report()
    print(f"\n{'='*60}")
    print(f"Nova v390 - Intelligence Supercharger Report")
    print(f"{'='*60}")
    print(f"  Report ID: {r.get('report_id','N/A')}")
    print(f"  Total Modules: {r.get('total_modules',0)}")
    print(f"  Supercharger Active: {r.get('supercharger_active',False)}")
    print(f"  Boost Factor: {r.get('boost_factor','N/A')}")
    print(f"  Modules Enhanced: {len(r.get('modules_enhanced',[]))}")
    print(f"{'='*60}\n")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
