#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v653_before_after_benchmark_comparator import compare_before_after_benchmarks
import json
def main(): r=compare_before_after_benchmarks(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v653_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
