#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v528_scan_secret_files import scan_secret_files
import json
def main(): r=scan_secret_files(); print(r.get("version","done")); (ROOT/"reports"/"v528_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
