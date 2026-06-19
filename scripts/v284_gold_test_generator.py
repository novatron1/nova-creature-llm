#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v284_test_generator import generate_tests
import json
def main():
    r=generate_tests()
    print(r.get("version","done"))
    (ROOT/"reports"/"v284_gold_test_generator_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
