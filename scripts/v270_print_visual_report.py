#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v270_visual_intelligence_report import generate_report
import json
def main():
    r=generate_report()
    print(r.get("version","done"))
    (ROOT/"reports"/"v270_print_visual_report_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
