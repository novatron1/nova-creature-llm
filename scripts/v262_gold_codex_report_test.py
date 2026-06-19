#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v262_codex_report_screenshot_parser import parse_report
import json
def main():
    r=parse_report()
    print(r.get("version","done"))
    (ROOT/"reports"/"v262_gold_codex_report_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
