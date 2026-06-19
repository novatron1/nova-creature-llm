#!/usr/bin/env python3
"""Aux."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v244_base_model_benchmark_before_swap import run_benchmark
def main():
    r=run_benchmark(); print(f'All: {r["all_passed"]}')
    import json
    (ROOT/"reports"/"v244_run_base_benchmark_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
