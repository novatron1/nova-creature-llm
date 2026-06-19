#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v658_hard_vs_gold_separator import separate_hard_vs_gold
import json
def main(): r=separate_hard_vs_gold(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v658_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
