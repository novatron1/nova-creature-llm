#!/usr/bin/env python3
"""Aux."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v242_model_compatibility_scanner import scan_compatibility
def main():
    r=scan_compatibility(); print(f'Exists: {r["exists"]}')
    import json
    (ROOT/"reports"/"v242_scan_model_compatibility_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
