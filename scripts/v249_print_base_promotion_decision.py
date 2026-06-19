#!/usr/bin/env python3
"""Aux."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v249_best_base_promotion_gate import check_gate
def main():
    r=check_gate(); print(f'Promote ready: {r["promote_ready"]}')
    import json
    (ROOT/"reports"/"v249_print_base_promotion_decision_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
