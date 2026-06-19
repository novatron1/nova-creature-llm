#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v266_screenshot_to_memory_converter import convert
import json
def main():
    r=convert()
    print(r.get("version","done"))
    (ROOT/"reports"/"v266_convert_screenshot_to_memory_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
