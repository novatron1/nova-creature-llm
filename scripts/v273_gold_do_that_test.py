#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v273_do_that_context_resolver import resolve_do_that
import json
def main():
    r=resolve_do_that()
    print(r.get("version","done"))
    (ROOT/"reports"/"v273_gold_do_that_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
