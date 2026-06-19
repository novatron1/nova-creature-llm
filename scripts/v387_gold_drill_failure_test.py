#!/usr/bin/env python3
"""Gold test for v387_drill_failure_response_planner."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v387_drill_failure_response_planner import plan_failure_response
def main():
    r = plan_failure_response()
    print(r.get("version","done"))
    (ROOT/"reports"/"v387_gold_drill_failure_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
