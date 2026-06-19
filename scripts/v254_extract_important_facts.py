#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v254_important_fact_extractor import extract_facts
import json
def main():
    r=extract_facts()
    print(r.get("version","done"))
    (ROOT/"reports"/"v254_extract_important_facts_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
