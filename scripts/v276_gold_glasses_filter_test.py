#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v276_glasses_mode_response_filter import filter_response
import json
def main():
    r=filter_response()
    print(r.get("version","done"))
    (ROOT/"reports"/"v276_gold_glasses_filter_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
