#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v391_research_experiment_planner_v2 import plan_experiment_v2
import json
def main():
    r = plan_experiment_v2()
    print(r.get("version","done"))
    (ROOT/"reports"/"v391_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__":
    raise SystemExit(main())
