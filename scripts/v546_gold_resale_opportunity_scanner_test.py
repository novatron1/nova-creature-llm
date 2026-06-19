#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v546_scan_resale_opportunity import scan_resale_opportunity
import json
def main(): r=scan_resale_opportunity(); print(r.get("version","done")); (ROOT/"reports"/"v546_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
