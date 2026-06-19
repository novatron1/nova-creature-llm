#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v251_long_term_memory_compressor import compress_memory
import json
def main():
    r=compress_memory()
    print(r.get("version","done"))
    (ROOT/"reports"/"v251_compress_memory_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
