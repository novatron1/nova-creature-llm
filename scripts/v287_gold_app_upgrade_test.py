#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v287_app_upgrade_planner import plan_upgrade
import json
def main():
    r=plan_upgrade()
    print(r.get("version","done"))
    (ROOT/"reports"/"v287_gold_app_upgrade_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
