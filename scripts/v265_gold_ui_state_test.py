#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v265_ui_state_detector import detect_ui
import json
def main():
    r=detect_ui()
    print(r.get("version","done"))
    (ROOT/"reports"/"v265_gold_ui_state_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
