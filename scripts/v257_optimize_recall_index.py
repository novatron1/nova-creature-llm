#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v257_recall_speed_optimizer import optimize_recall
import json
def main():
    r=optimize_recall()
    print(r.get("version","done"))
    (ROOT/"reports"/"v257_optimize_recall_index_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
