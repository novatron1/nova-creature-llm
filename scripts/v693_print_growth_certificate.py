#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v693_proven_growth_certificate import certify_proven_growth; import json
def main(): r=certify_proven_growth(); print(r.get("version","done")); (ROOT/"reports"/"v693_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
