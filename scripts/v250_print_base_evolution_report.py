#!/usr/bin/env python3
"""Aux."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v250_base_model_evolution_report import generate_report
def main():
    r=generate_report(); print(f'Current: {r["current_base"]}, Ready: {r["promotion_ready"]}')
    import json
    (ROOT/"reports"/"v250_print_base_evolution_report_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
