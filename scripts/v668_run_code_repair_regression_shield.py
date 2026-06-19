#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v668_code_repair_regression_shield import run_code_repair_regression_shield
import json
def main(): r=run_code_repair_regression_shield(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v668_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
