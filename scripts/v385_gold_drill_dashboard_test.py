#!/usr/bin/env python3
"""Gold test for v385_drill_performance_dashboard."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v385_drill_performance_dashboard import generate_drill_dashboard
def main():
    r = generate_drill_dashboard()
    print(r.get("version","done"))
    (ROOT/"reports"/"v385_gold_drill_dashboard_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
