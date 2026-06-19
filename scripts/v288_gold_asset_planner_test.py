#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v288_game_app_asset_planner import plan_assets
import json
def main():
    r=plan_assets()
    print(r.get("version","done"))
    (ROOT/"reports"/"v288_gold_asset_planner_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
