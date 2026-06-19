#!/usr/bin/env python3
"""Aux script."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v232_code_repair_dataset_cleaner import clean_dataset
def main():
    r=clean_dataset(); print(f'Clean: {r["clean"]}, Removed: {r["removed"]}')
    import json
    (ROOT/"reports"/"v232_clean_code_repair_dataset_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
