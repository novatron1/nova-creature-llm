#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v663_drill_to_training_converter import convert_drills_to_training
import json
def main(): r=convert_drills_to_training(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v663_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
