#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v271_voice_command_resolver import resolve
import json
def main():
    r=resolve()
    print(r.get("version","done"))
    (ROOT/"reports"/"v271_gold_voice_command_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
