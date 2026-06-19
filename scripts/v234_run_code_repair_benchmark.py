#!/usr/bin/env python3
"""Aux script."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v234_code_repair_benchmark_2 import run_benchmark
def main():
    r=run_benchmark(); print(f'{r["passed"]}/{r["total"]} pass')
    import json
    (ROOT/"reports"/"v234_run_code_repair_benchmark_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
