#!/usr/bin/env python3
"""Gold test for v372_drill_memory_capturer."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v372_drill_memory_capturer import capture_drill_memory
def main():
    r = capture_drill_memory()
    print(r.get("version","done"))
    (ROOT/"reports"/"v372_gold_drill_memory_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
