#!/usr/bin/env python3
"""Aux."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v243_tokenizer_compatibility_check import check_tokenizer
def main():
    r=check_tokenizer(); print(f'Blocker: {r["blocker"]}')
    import json
    (ROOT/"reports"/"v243_scan_tokenizer_compatibility_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
