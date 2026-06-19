#!/usr/bin/env python3
"""Gold test for v368_training_candidate_scorer."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v368_training_candidate_scorer import score_candidate
def main():
    r = score_candidate()
    print(r.get("version","done"))
    (ROOT/"reports"/"v368_gold_candidate_scorer_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
