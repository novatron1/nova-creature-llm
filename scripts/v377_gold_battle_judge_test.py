#!/usr/bin/env python3
"""Gold test for v377_battle_judge."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v377_battle_judge import judge_battle
def main():
    r = judge_battle()
    print(r.get("version","done"))
    (ROOT/"reports"/"v377_gold_battle_judge_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
