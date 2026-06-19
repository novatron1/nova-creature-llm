#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v298_human_distance_safety_rule import check_distance
import json
def main():
    r=check_distance()
    print(r.get("version","done"))
    (ROOT/"reports"/"v298_gold_human_distance_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
