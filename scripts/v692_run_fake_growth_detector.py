#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v692_fake_intelligence_growth_detector import detect_fake_intelligence_growth; import json
def main(): r=detect_fake_intelligence_growth(); print(r.get("version","done")); (ROOT/"reports"/"v692_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
