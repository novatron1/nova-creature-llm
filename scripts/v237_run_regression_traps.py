#!/usr/bin/env python3
"""Aux script."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v237_planner_regression_trap_test import run_traps
def main():
    r=run_traps(); print(f'Traps: {r["total"]}, all: {r["all_passed"]}')
    import json
    (ROOT/"reports"/"v237_run_regression_traps_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
