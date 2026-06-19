#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v670_growth_proof_report import generate_planner_growth_proof_report
import json
def main(): r=generate_planner_growth_proof_report(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v670_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
