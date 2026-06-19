#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v527_detect_api_key_leak import detect_api_key_leak
import json
def main(): r=detect_api_key_leak(); print(r.get("version","done")); (ROOT/"reports"/"v527_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
