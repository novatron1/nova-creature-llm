#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v657_cross_role_damage_detector import detect_cross_role_damage
import json
def main(): r=detect_cross_role_damage(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v657_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
