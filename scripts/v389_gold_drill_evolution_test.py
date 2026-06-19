#!/usr/bin/env python3
"""Gold test for v389_drill_evolution_engine."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v389_drill_evolution_engine import evolve_drill
def main():
    r = evolve_drill()
    print(r.get("version","done"))
    (ROOT/"reports"/"v389_gold_drill_evolution_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
