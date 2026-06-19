#!/usr/bin/env python3
"""Gold test for v373_drill_consistency_report."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v373_drill_consistency_report import generate_consistency_report
def main():
    r = generate_consistency_report()
    print(r.get("version","done"))
    (ROOT/"reports"/"v373_gold_drill_consistency_report_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
