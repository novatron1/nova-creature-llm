#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v259_memory_to_training_cleaner import clean_memory
import json
def main():
    r=clean_memory()
    print(r.get("version","done"))
    (ROOT/"reports"/"v259_clean_memory_for_training_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
