#!/usr/bin/env python3
"""Gold test for v361_drill_intelligence_engine."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v361_drill_intelligence_engine import run_drill
def main():
    r = run_drill()
    print(r.get("version","done"))
    (ROOT/"reports"/"v361_gold_intelligence_drill_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
