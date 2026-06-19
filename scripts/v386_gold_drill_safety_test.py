#!/usr/bin/env python3
"""Gold test for v386_drill_safety_checker."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v386_drill_safety_checker import check_drill_safety
def main():
    r = check_drill_safety()
    print(r.get("version","done"))
    (ROOT/"reports"/"v386_gold_drill_safety_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
