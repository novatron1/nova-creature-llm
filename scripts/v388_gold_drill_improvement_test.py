#!/usr/bin/env python3
"""Gold test for v388_drill_improvement_recommender."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v388_drill_improvement_recommender import recommend_drill_improvement
def main():
    r = recommend_drill_improvement()
    print(r.get("version","done"))
    (ROOT/"reports"/"v388_gold_drill_improvement_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
