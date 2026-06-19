#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v560_generate_money_report import generate_money_report
import json
def main(): r=generate_money_report(); print(r.get("version","done")); (ROOT/"reports"/"v560_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
