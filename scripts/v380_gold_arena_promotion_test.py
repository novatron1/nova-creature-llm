#!/usr/bin/env python3
"""Gold test for v380_arena_promotion_gate."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v380_arena_promotion_gate import gate_promotion
def main():
    r = gate_promotion()
    print(r.get("version","done"))
    (ROOT/"reports"/"v380_gold_arena_promotion_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
