#!/usr/bin/env python3
"""Aux."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v241_stronger_base_model_loader import scan_base_models
def main():
    r=scan_base_models(); print(f'Found: {r["count"]}')
    import json
    (ROOT/"reports"/"v241_scan_base_models_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
