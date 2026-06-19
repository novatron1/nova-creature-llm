#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v420_self_improvement_lab_report import generate_self_improvement_lab_report
import json
def main():
    r = generate_self_improvement_lab_report()
    print(r.get("version","done"))
    (ROOT/"reports"/"v420_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__":
    raise SystemExit(main())
