#!/usr/bin/env python3
"""Aux script."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v238_planner_promotion_decision import decide
def main():
    r=decide(); print(f'Decision: {r["decision"]}, Winner: {r["winner"]}')
    import json
    (ROOT/"reports"/"v238_print_promotion_decision_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
