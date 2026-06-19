#!/usr/bin/env python3
"""Gold test for v378_battle_score_history."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v378_battle_score_history import track_battle_history
def main():
    r = track_battle_history()
    print(r.get("version","done"))
    (ROOT/"reports"/"v378_gold_battle_history_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
