#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v269_vision_claim_firewall import filter_claim
import json
def main():
    r=filter_claim()
    print(r.get("version","done"))
    (ROOT/"reports"/"v269_gold_vision_claim_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
