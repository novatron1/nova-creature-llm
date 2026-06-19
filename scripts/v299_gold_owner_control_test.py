#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v299_owner_manual_control_gate import check_control
import json
def main():
    r=check_control()
    print(r.get("version","done"))
    (ROOT/"reports"/"v299_gold_owner_control_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
