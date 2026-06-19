#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v256_memory_priority_system import rank_priority
import json
def main():
    r=rank_priority()
    print(r.get("version","done"))
    (ROOT/"reports"/"v256_rank_memory_priority_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
