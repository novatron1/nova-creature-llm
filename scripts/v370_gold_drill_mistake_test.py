#!/usr/bin/env python3
"""Gold test for v370_drill_mistake_logger."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v370_drill_mistake_logger import log_drill_mistake
def main():
    r = log_drill_mistake()
    print(r.get("version","done"))
    (ROOT/"reports"/"v370_gold_drill_mistake_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
