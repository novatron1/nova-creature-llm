#!/usr/bin/env python3
"""Gold test for v376_checkpoint_battle_arena."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v376_checkpoint_battle_arena import run_checkpoint_battle
def main():
    r = run_checkpoint_battle()
    print(r.get("version","done"))
    (ROOT/"reports"/"v376_gold_checkpoint_arena_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
