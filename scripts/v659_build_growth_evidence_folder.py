#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v659_real_growth_evidence_folder import build_growth_evidence_folder
import json
def main(): r=build_growth_evidence_folder(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v659_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
