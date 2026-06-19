#!/usr/bin/env python3
"""Gold test for v381_drill_difficulty_calibrator."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v381_drill_difficulty_calibrator import calibrate_drill_difficulty
def main():
    r = calibrate_drill_difficulty()
    print(r.get("version","done"))
    (ROOT/"reports"/"v381_gold_drill_calibrator_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
