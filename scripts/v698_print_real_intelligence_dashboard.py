#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v698_real_intelligence_dashboard import generate_real_intelligence_dashboard; import json
def main(): r=generate_real_intelligence_dashboard(); print(r.get("version","done")); (ROOT/"reports"/"v698_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
