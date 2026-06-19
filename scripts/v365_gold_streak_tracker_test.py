#!/usr/bin/env python3
"""Gold test for v365_streak_consistency_tracker."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v365_streak_consistency_tracker import track_streak
def main():
    r = track_streak()
    print(r.get("version","done"))
    (ROOT/"reports"/"v365_gold_streak_tracker_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
