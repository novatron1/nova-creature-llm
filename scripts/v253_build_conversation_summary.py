#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v253_conversation_summary_memory import build_summary
import json
def main():
    r=build_summary()
    print(r.get("version","done"))
    (ROOT/"reports"/"v253_build_conversation_summary_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
