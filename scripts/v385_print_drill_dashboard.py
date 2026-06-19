#!/usr/bin/env python3
"""Print Drill Performance Dashboard."""
from __future__ import annotations
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v385_drill_performance_dashboard import generate_drill_dashboard
def main():
    r = generate_drill_dashboard()
    print(f"\n{'='*60}")
    print(f"Nova v385 - Drill Performance Dashboard")
    print(f"{'='*60}")
    metrics = r.get('metrics',{})
    print(f"  Dashboard ID: {r.get('dashboard_id','N/A')}")
    print(f"  Overall: {r.get('overall','N/A')}")
    for k,v in metrics.items():
        print(f"  {k}: {v}")
    print(f"{'='*60}\n")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
