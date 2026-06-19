#!/usr/bin/env python3
"""Print v403_self_improvement_dashboard — Self-Improvement Dashboard."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v403_self_improvement_dashboard import generate_self_improvement_dashboard
def main():
    r = generate_self_improvement_dashboard()
    print(f"\n{'='*60}")
    print(f"  v403_self_improvement_dashboard — Self-Improvement Dashboard")
    print(f"{'='*60}")
    if isinstance(r,dict):
        for k,v in r.items():
            print(f"  {k}: {v}")
    print(f"{'='*60}\n")
if __name__=="__main__":
    raise SystemExit(main())
