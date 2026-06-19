#!/usr/bin/env python3
"""Gold test for v390_intelligence_supercharger_report."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v390_intelligence_supercharger_report import generate_supercharger_report
def main():
    r = generate_supercharger_report()
    print(r.get("version","done"))
    (ROOT/"reports"/"v390_gold_supercharger_report_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
