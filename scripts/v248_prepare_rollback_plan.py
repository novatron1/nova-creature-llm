#!/usr/bin/env python3
"""Aux."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v248_model_swap_rollback import prepare_rollback
def main():
    r=prepare_rollback(); print(f'Rollback: {r["rollback_ready"]}')
    import json
    (ROOT/"reports"/"v248_prepare_rollback_plan_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
