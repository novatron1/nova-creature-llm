#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v263_error_screenshot_detector import detect_errors
import json
def main():
    r=detect_errors()
    print(r.get("version","done"))
    (ROOT/"reports"/"v263_gold_error_screenshot_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
