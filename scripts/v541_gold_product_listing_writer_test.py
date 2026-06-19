#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v541_write_product_listing import write_product_listing
import json
def main(): r=write_product_listing(); print(r.get("version","done")); (ROOT/"reports"/"v541_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
