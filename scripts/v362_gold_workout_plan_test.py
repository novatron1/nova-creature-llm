#!/usr/bin/env python3
"""Gold test for v362_role_brain_workout_plan."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v362_role_brain_workout_plan import generate_workout_plan
def main():
    r = generate_workout_plan()
    print(r.get("version","done"))
    (ROOT/"reports"/"v362_gold_workout_plan_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
