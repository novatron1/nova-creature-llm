#!/usr/bin/env python3
"""Aux script."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v240_code_repair_growth_report import generate_report
def main():
    r=generate_report(); print(f'Before: {r["before_score"]}, After: {r["after_score"]}')
    import json
    (ROOT/"reports"/"v240_print_code_repair_growth_report_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
