#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v694_next_training_target_selector import select_next_training_target; import json
def main(): r=select_next_training_target(); print(r.get("version","done")); (ROOT/"reports"/"v694_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
