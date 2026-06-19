#!/usr/bin/env python3
"""Gold test for v379_arena_leaderboard."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v379_arena_leaderboard import calculate_leaderboard
def main():
    r = calculate_leaderboard()
    print(r.get("version","done"))
    (ROOT/"reports"/"v379_gold_arena_leaderboard_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
