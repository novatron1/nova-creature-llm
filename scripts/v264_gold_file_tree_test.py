#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v264_file_tree_screenshot_reader import read_tree
import json
def main():
    r=read_tree()
    print(r.get("version","done"))
    (ROOT/"reports"/"v264_gold_file_tree_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
