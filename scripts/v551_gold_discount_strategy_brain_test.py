#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v551_suggest_discount import suggest_discount
import json
def main(): r=suggest_discount(); print(r.get("version","done")); (ROOT/"reports"/"v551_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
