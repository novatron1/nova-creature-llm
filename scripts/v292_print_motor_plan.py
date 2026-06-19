#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v292_motor_controller_interface_plan import plan_motor
import json
def main():
    r=plan_motor()
    print(r.get("version","done"))
    (ROOT/"reports"/"v292_print_motor_plan_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
