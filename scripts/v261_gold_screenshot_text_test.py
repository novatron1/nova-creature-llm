#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v261_screenshot_text_reader import read_text
import json
def main():
    r=read_text()
    print(r.get("version","done"))
    (ROOT/"reports"/"v261_gold_screenshot_text_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
