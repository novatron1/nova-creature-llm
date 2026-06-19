#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v275_voice_safety_confirmation import confirm
import json
def main():
    r=confirm()
    print(r.get("version","done"))
    (ROOT/"reports"/"v275_gold_voice_safety_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
