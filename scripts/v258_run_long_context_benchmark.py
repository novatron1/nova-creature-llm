#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v258_long_context_benchmark import run_benchmark
import json
def main():
    r=run_benchmark()
    print(r.get("version","done"))
    (ROOT/"reports"/"v258_run_long_context_benchmark_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
