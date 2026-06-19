#!/usr/bin/env python3
"""Gold test for v363_weakness_focused_drill_parser."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v363_weakness_focused_drill_parser import parse_weakness_drill
def main():
    r = parse_weakness_drill()
    print(r.get("version","done"))
    (ROOT/"reports"/"v363_gold_weakness_drill_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
