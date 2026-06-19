#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v295_sim_to_hardware_gap_report import gap_report
import json
def main():
    r=gap_report()
    print(r.get("version","done"))
    (ROOT/"reports"/"v295_print_gap_report_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
