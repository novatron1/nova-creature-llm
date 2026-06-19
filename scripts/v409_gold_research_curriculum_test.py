#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v409_research_curriculum_builder import build_research_curriculum
import json
def main():
    r = build_research_curriculum()
    print(r.get("version","done"))
    (ROOT/"reports"/"v409_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__":
    raise SystemExit(main())
