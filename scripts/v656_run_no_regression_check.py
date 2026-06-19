#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v656_improvement_without_regression_checker import check_improvement_without_regression
import json
def main(): r=check_improvement_without_regression(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v656_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
