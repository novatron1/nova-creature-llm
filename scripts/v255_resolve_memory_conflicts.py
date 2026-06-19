#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v255_memory_conflict_resolver import resolve_conflicts
import json
def main():
    r=resolve_conflicts()
    print(r.get("version","done"))
    (ROOT/"reports"/"v255_resolve_memory_conflicts_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
