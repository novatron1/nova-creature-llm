#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v691_real_intelligence_proof import check_real_intelligence_proof; import json
def main(): r=check_real_intelligence_proof(); print(r.get("version","done")); (ROOT/"reports"/"v691_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
