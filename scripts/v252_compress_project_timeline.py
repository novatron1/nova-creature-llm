#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v252_project_timeline_compressor import compress_timeline
import json
def main():
    r=compress_timeline()
    print(r.get("version","done"))
    (ROOT/"reports"/"v252_compress_project_timeline_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
