#!/usr/bin/env python3
"""Aux script."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v235_planner_candidate_checkpoint_builder import build_checkpoint
def main():
    r=build_checkpoint(); print(f'Created: {r["checkpoint_created"]}, Blocked: {r["blocked_by"]}')
    import json
    (ROOT/"reports"/"v235_build_planner_checkpoint_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
