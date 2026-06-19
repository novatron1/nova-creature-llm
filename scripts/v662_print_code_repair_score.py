#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v662_code_repair_score_tracker import track_code_repair_score
import json
def main(): r=track_code_repair_score(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v662_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
