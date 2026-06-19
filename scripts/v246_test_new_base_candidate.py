#!/usr/bin/env python3
"""Aux."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v246_new_base_candidate_test import test_candidate
def main():
    r=test_candidate(); print(f'Found: {r["candidate_found"]}')
    import json
    (ROOT/"reports"/"v246_test_new_base_candidate_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
