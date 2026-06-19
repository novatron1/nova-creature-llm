#!/usr/bin/env python3
"""Gold test for v366_role_brain_fitness_score."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v366_role_brain_fitness_score import calculate_fitness
def main():
    r = calculate_fitness()
    print(r.get("version","done"))
    (ROOT/"reports"/"v366_gold_fitness_score_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
