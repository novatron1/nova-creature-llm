#!/usr/bin/env python3
"""Gold test for v383_drill_curriculum_scheduler."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v383_drill_curriculum_scheduler import schedule_curriculum
def main():
    r = schedule_curriculum()
    print(r.get("version","done"))
    (ROOT/"reports"/"v383_gold_drill_curriculum_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
