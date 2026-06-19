#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v534_plan_account_recovery import plan_account_recovery
import json
def main(): r=plan_account_recovery(); print(r.get("version","done")); (ROOT/"reports"/"v534_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
