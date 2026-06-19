#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v294_emergency_stop_hardware_checklist import checklist
import json
def main():
    r=checklist()
    print(r.get("version","done"))
    (ROOT/"reports"/"v294_print_estop_checklist_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
