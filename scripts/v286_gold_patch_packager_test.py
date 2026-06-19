#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v286_patch_packager import package_patch
import json
def main():
    r=package_patch()
    print(r.get("version","done"))
    (ROOT/"reports"/"v286_gold_patch_packager_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
