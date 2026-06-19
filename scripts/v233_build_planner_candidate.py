#!/usr/bin/env python3
"""Aux script."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v233_planner_finetune_candidate_builder import build_candidate
def main():
    r=build_candidate(); print(f'Blocked: {r["blocked_by"]}, v055: {r["v055_preserved"]}')
    import json
    (ROOT/"reports"/"v233_build_planner_candidate_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
