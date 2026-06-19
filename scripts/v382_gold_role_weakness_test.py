#!/usr/bin/env python3
"""Gold test for v382_role_brain_weakness_detector_3."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v382_role_brain_weakness_detector_3 import detect_role_weaknesses
def main():
    r = detect_role_weaknesses()
    print(r.get("version","done"))
    (ROOT/"reports"/"v382_gold_role_weakness_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
