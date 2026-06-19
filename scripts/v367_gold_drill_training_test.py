#!/usr/bin/env python3
"""Gold test for v367_drill_to_training_converter."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v367_drill_to_training_converter import convert_drill_to_training
def main():
    r = convert_drill_to_training()
    print(r.get("version","done"))
    (ROOT/"reports"/"v367_gold_drill_training_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
