#!/usr/bin/env python3
"""Aux."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v247_base_vs_v055_tournament import run_tournament
def main():
    r=run_tournament(); print(f'Winner: {r["winner"]}')
    import json
    (ROOT/"reports"/"v247_run_base_tournament_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
