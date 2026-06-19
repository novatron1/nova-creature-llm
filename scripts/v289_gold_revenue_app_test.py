#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v289_revenue_app_builder_mode import plan_revenue_app
import json
def main():
    r=plan_revenue_app()
    print(r.get("version","done"))
    (ROOT/"reports"/"v289_gold_revenue_app_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
