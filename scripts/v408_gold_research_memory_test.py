#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v408_research_memory_capturer import capture_research_memory
import json
def main():
    r = capture_research_memory()
    print(r.get("version","done"))
    (ROOT/"reports"/"v408_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__":
    raise SystemExit(main())
