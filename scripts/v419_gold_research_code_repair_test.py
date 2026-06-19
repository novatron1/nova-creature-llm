#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v419_research_code_repair_analyzer import analyze_research_code_repair
import json
def main():
    r = analyze_research_code_repair()
    print(r.get("version","done"))
    (ROOT/"reports"/"v419_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__":
    raise SystemExit(main())
