#!/usr/bin/env python3
"""Gold test for v371_drill_benchmark_runner."""
from __future__ import annotations
import sys;from pathlib import Path; import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v371_drill_benchmark_runner import run_drill_benchmark
def main():
    r = run_drill_benchmark()
    print(r.get("version","done"))
    (ROOT/"reports"/"v371_gold_drill_benchmark_test.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
