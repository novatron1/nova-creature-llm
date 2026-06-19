#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v282_sandbox_file_builder import build_file
import json
def main():
    r=build_file()
    print(r.get("version","done"))
    (ROOT/"reports"/"v282_gold_file_builder_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
