#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v654_intelligence_gain_meter_2 import calculate_intelligence_gain_2
import json
def main(): r=calculate_intelligence_gain_2(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v654_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
