#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v544_calculate_profit_margin import calculate_profit_margin
import json
def main(): r=calculate_profit_margin(); print(r.get("version","done")); (ROOT/"reports"/"v544_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
