#!/usr/bin/env python3
"""Aux."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v245_role_brain_transfer_adapter import plan_transfer
def main():
    r=plan_transfer(); print(f'Roles: {len(r["roles"])}')
    import json
    (ROOT/"reports"/"v245_plan_role_transfer_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
