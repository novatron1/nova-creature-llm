#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v661_planner_code_repair_hard_benchmark_3 import run_planner_code_repair_hard_benchmark_3
import json
def main(): r=run_planner_code_repair_hard_benchmark_3(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v661_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
