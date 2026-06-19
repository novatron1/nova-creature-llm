#!/usr/bin/env python3
"""Gold test for v375_checkpoint_candidate_builder."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v375_checkpoint_candidate_builder import build_drill_checkpoint
def main():
    r = build_drill_checkpoint()
    print(r.get("version","done"))
    (ROOT/"reports"/"v375_gold_drill_checkpoint_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
