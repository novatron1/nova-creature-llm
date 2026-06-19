#!/usr/bin/env python3
"""Aux script."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v231_planner_code_repair_training_batch import build_planner_batch
def main():
    r=build_planner_batch(); print(f'Batch: {r["total"]} lessons')
    import json
    (ROOT/"reports"/"v231_build_planner_code_repair_batch_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
